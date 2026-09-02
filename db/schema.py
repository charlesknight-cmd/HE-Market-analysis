import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from config import DB_PATH

CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT    UNIQUE NOT NULL,   -- e.g. "DRR304" from the jobs.ac.uk URL
    title         TEXT    NOT NULL,
    institution   TEXT,
    department    TEXT,
    salary_raw    TEXT,                      -- raw string as it appears on site
    salary_min    REAL,                      -- lower bound parsed to £
    salary_max    REAL,                      -- upper bound parsed to £
    closing_date  TEXT,                      -- YYYY-MM-DD
    contract_type TEXT,                      -- 'permanent' | 'fixed-term'
    hours         TEXT,                      -- 'full-time' | 'part-time' | 'flexible'
    category      TEXT,                      -- subject-discipline slug (see config.DISCIPLINES)
    url           TEXT    NOT NULL,
    first_seen    TEXT    NOT NULL,          -- ISO-8601 datetime (UTC)
    last_seen     TEXT    NOT NULL           -- ISO-8601 datetime (UTC)
)
"""

# One row per (job, subject-area tag). jobs.ac.uk tags a job with any number of
# academic disciplines (the 21 facets we scrape), their sub-disciplines, and
# non-academic disciplines; the detail page lists them all. `jobs.category` only
# records the facet a job was first scraped under, so this table is the source
# of truth for discipline attribution (see the jobs_by_discipline view below).
CREATE_JOB_DISCIPLINES = """
CREATE TABLE IF NOT EXISTS job_disciplines (
    job_id      TEXT NOT NULL,
    facet       TEXT NOT NULL,   -- 'academic' | 'sub' | 'non-academic'
    slug        TEXT NOT NULL,   -- e.g. 'computer-sciences', 'social-policy'
    name        TEXT,            -- display name from the detail page (NULL if recovered from a redirect URL)
    parent_slug TEXT,            -- for 'sub': the academic discipline it sits under
    source      TEXT NOT NULL,   -- 'listing' | 'redirect' | 'detail' (ascending authority)
    position    INTEGER,         -- order on the detail page (0 = first); NULL for listing-sourced rows
    first_seen  TEXT NOT NULL,   -- ISO-8601 datetime (UTC)
    last_seen   TEXT NOT NULL,   -- ISO-8601 datetime (UTC)
    PRIMARY KEY (job_id, facet, slug)
)
"""

CREATE_SCRAPE_RUNS = """
CREATE TABLE IF NOT EXISTS scrape_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at       TEXT    NOT NULL,         -- ISO-8601 datetime (UTC)
    category     TEXT    NOT NULL,
    jobs_found   INTEGER DEFAULT 0,
    jobs_new     INTEGER DEFAULT 0,
    jobs_updated INTEGER DEFAULT 0,
    status       TEXT    NOT NULL,         -- 'ok' | 'error'
    error        TEXT
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_jobs_institution   ON jobs (institution)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_category      ON jobs (category)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_first_seen    ON jobs (first_seen)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_last_seen     ON jobs (last_seen)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_contract_type ON jobs (contract_type)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_hours         ON jobs (hours)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_region        ON jobs (region)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_enriched_at   ON jobs (enriched_at)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_disciplines_at ON jobs (disciplines_at)",
    "CREATE INDEX IF NOT EXISTS idx_jd_facet_slug      ON job_disciplines (facet, slug)",
]

# Columns of `jobs` that the discipline views pass through unchanged — everything
# except `category`, which they replace. Resolved at init time from the live
# table so a later ALTER TABLE migration is picked up automatically.
def _jobs_passthrough_columns(conn: sqlite3.Connection) -> list[str]:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(jobs)")]
    return [c for c in cols if c != "category"]


def _view_definitions(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """(name, CREATE VIEW sql) for the two discipline views.

    jobs_by_discipline — one row per job x academic discipline (the 21 facets).
        A job tagged with three disciplines appears three times, each with
        `category` set to that discipline, so GROUP BY category counts it under
        each. Jobs with no row in job_disciplines yet (not backfilled) fall back
        to their scraped `jobs.category`, so the view is never emptier than the
        table. `position` is the detail-page order (NULL for fallback/listing rows).

    jobs_primary_discipline — exactly one row per job, with `category` set to the
        job's first-listed academic discipline (falling back to jobs.category).
        For queries where a job must count once (salary histograms, per-job
        baselines) but still needs a discipline label.
    """
    cols = ", ".join(f"j.{c}" for c in _jobs_passthrough_columns(conn))
    return [
        ("jobs_by_discipline", f"""
        CREATE VIEW jobs_by_discipline AS
        SELECT {cols}, d.slug AS category, d.position AS position
        FROM jobs j
        JOIN job_disciplines d ON d.job_id = j.job_id AND d.facet = 'academic'
        UNION ALL
        SELECT {cols}, j.category AS category, NULL AS position
        FROM jobs j
        WHERE NOT EXISTS (
            SELECT 1 FROM job_disciplines d
            WHERE d.job_id = j.job_id AND d.facet = 'academic'
        )
        """),
        ("jobs_primary_discipline", f"""
        CREATE VIEW jobs_primary_discipline AS
        SELECT {cols},
               COALESCE(
                   (SELECT d.slug FROM job_disciplines d
                    WHERE d.job_id = j.job_id AND d.facet = 'academic'
                    ORDER BY d.position IS NULL, d.position, d.slug
                    LIMIT 1),
                   j.category
               ) AS category
        FROM jobs j
        """),
    ]


def _ensure_views(conn: sqlite3.Connection) -> None:
    """Create the discipline views, recreating one only if its SQL has changed.

    Both the scraper and the dashboard call init_db(); dropping and recreating a
    view on every start would briefly take a write lock the other may be
    holding, so an unchanged view is left alone.
    """
    norm = lambda sql: " ".join(sql.split())
    for name, sql in _view_definitions(conn):
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'view' AND name = ?", (name,)
        ).fetchone()
        if row and norm(row[0]) == norm(sql):
            continue
        conn.execute(f"DROP VIEW IF EXISTS {name}")
        conn.execute(sql)

# Columns added after initial release — ALTER TABLE is safe to run repeatedly
_MIGRATIONS = [
    ("closing_date",  "TEXT"),
    ("contract_type", "TEXT"),
    ("hours",         "TEXT"),
    ("location",      "TEXT"),   # town/city from detail-page enrichment
    ("region",        "TEXT"),   # UK nation (England/Scotland/Wales/NI) or "International"
    ("date_posted",   "TEXT"),   # YYYY-MM-DD from JSON-LD datePosted (true posting date)
    ("enriched_at",   "TEXT"),   # ISO-8601 UTC; NULL = not yet enriched
    ("disciplines_at", "TEXT"),  # ISO-8601 UTC; when the detail page's subject areas were last captured (NULL = pending backfill)
]


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Open a connection for one unit of work: ``with get_connection() as conn:``.

    Commits on a clean exit, rolls back on an exception (sqlite3's own context
    manager), and always *closes* the connection afterwards. A bare
    ``sqlite3.connect`` used as a context manager only commits — it never
    closes — and on Python 3.14 the connection is not reclaimed when it goes
    out of scope either, so every call leaked two file descriptors (db + WAL).
    A long loop of per-job writes (the discipline backfill) hit the 1024-fd
    limit after ~500 jobs with "unable to open database file".
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        with conn:
            yield conn
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add new columns to an existing database. Safe to run on a fresh DB too."""
    for col_name, col_type in _MIGRATIONS:
        try:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
            conn.commit()
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise  # unexpected error — don't swallow it


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(CREATE_JOBS)
        conn.execute(CREATE_JOB_DISCIPLINES)
        conn.execute(CREATE_SCRAPE_RUNS)
        _migrate(conn)
        for idx in CREATE_INDEXES:
            conn.execute(idx)
        _ensure_views(conn)
        conn.commit()
    print(f"Database ready at {DB_PATH}")
