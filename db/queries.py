import sqlite3
from datetime import datetime, timezone
from typing import Any

from db.schema import get_connection


def _now() -> str:
    # Store as plain UTC string — SQLite's strftime can't parse the +00:00 suffix
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def upsert_job(conn: sqlite3.Connection, job: dict[str, Any]) -> str:
    """Insert a new job or update last_seen for an existing one.

    Returns 'new' or 'updated'.
    """
    now = _now()
    # Check existence before the upsert so the return value is race-condition-free
    already_exists = conn.execute(
        "SELECT 1 FROM jobs WHERE job_id = ?", (job["job_id"],)
    ).fetchone() is not None

    conn.execute(
        """
        INSERT INTO jobs
            (job_id, title, institution, department, salary_raw,
             salary_min, salary_max, closing_date, contract_type, hours,
             category, url, first_seen, last_seen)
        VALUES
            (:job_id, :title, :institution, :department, :salary_raw,
             :salary_min, :salary_max, :closing_date, :contract_type, :hours,
             :category, :url, :now, :now)
        ON CONFLICT(job_id) DO UPDATE SET
            last_seen     = excluded.last_seen,
            closing_date  = COALESCE(excluded.closing_date,  closing_date),
            contract_type = COALESCE(excluded.contract_type, contract_type),
            hours         = COALESCE(excluded.hours,         hours)
        """,
        {**job, "now": now},
    )
    return "updated" if already_exists else "new"


def bulk_upsert(jobs: list[dict[str, Any]]) -> tuple[int, int]:
    """Upsert a list of job dicts. Returns (new_count, updated_count)."""
    now = _now()
    new_count = updated_count = 0
    with get_connection() as conn:
        for job in jobs:
            existing = conn.execute(
                "SELECT id FROM jobs WHERE job_id = ?", (job["job_id"],)
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO jobs
                        (job_id, title, institution, department, salary_raw,
                         salary_min, salary_max, closing_date, contract_type, hours,
                         category, url, first_seen, last_seen)
                    VALUES
                        (:job_id, :title, :institution, :department, :salary_raw,
                         :salary_min, :salary_max, :closing_date, :contract_type, :hours,
                         :category, :url, :now, :now)
                    """,
                    {**job, "now": now},
                )
                new_count += 1
            else:
                conn.execute(
                    """
                    UPDATE jobs SET
                        last_seen     = ?,
                        closing_date  = COALESCE(?, closing_date),
                        contract_type = COALESCE(?, contract_type),
                        hours         = COALESCE(?, hours)
                    WHERE job_id = ?
                    """,
                    (now,
                     job.get("closing_date"), job.get("contract_type"), job.get("hours"),
                     job["job_id"]),
                )
                updated_count += 1
        conn.commit()
    return new_count, updated_count


def log_run(
    category: str,
    jobs_found: int,
    jobs_new: int,
    jobs_updated: int,
    status: str,
    error: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO scrape_runs
                (run_at, category, jobs_found, jobs_new, jobs_updated, status, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), category, jobs_found, jobs_new, jobs_updated, status, error),
        )
        conn.commit()


def get_all_jobs() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY first_seen DESC").fetchall()
    return [dict(r) for r in rows]


def get_jobs_since(days: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE first_seen >= datetime('now', ?)
            ORDER BY first_seen DESC
            """,
            (f"-{days} days",),
        ).fetchall()
    return [dict(r) for r in rows]
