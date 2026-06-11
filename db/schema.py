import sqlite3
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
]

# Columns added after initial release — ALTER TABLE is safe to run repeatedly
_MIGRATIONS = [
    ("closing_date",  "TEXT"),
    ("contract_type", "TEXT"),
    ("hours",         "TEXT"),
    ("location",      "TEXT"),   # town/city from detail-page enrichment
    ("region",        "TEXT"),   # UK nation (England/Scotland/Wales/NI) or "International"
    ("date_posted",   "TEXT"),   # YYYY-MM-DD from JSON-LD datePosted (true posting date)
    ("enriched_at",   "TEXT"),   # ISO-8601 UTC; NULL = not yet enriched
]


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


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
        conn.execute(CREATE_SCRAPE_RUNS)
        _migrate(conn)
        for idx in CREATE_INDEXES:
            conn.execute(idx)
        conn.commit()
    print(f"Database ready at {DB_PATH}")
