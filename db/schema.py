import sqlite3
from pathlib import Path

from config import DB_PATH

CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT    UNIQUE NOT NULL,   -- e.g. "DRR304" from the jobs.ac.uk URL
    title       TEXT    NOT NULL,
    institution TEXT,
    department  TEXT,
    salary_raw  TEXT,                      -- raw string as it appears on site
    salary_min  REAL,                      -- lower bound parsed to £
    salary_max  REAL,                      -- upper bound parsed to £
    category    TEXT,                      -- RSS feed category slug
    url         TEXT    NOT NULL,
    first_seen  TEXT    NOT NULL,          -- ISO-8601 datetime (UTC)
    last_seen   TEXT    NOT NULL           -- ISO-8601 datetime (UTC)
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
    "CREATE INDEX IF NOT EXISTS idx_jobs_institution ON jobs (institution)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_category    ON jobs (category)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_first_seen  ON jobs (first_seen)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_last_seen   ON jobs (last_seen)",
]


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(CREATE_JOBS)
        conn.execute(CREATE_SCRAPE_RUNS)
        for idx in CREATE_INDEXES:
            conn.execute(idx)
        conn.commit()
    print(f"Database ready at {DB_PATH}")
