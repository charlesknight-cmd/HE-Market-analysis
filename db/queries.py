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
    if not jobs:
        return 0, 0
    now = _now()
    new_count = updated_count = 0
    job_ids = [j["job_id"] for j in jobs]
    
    with get_connection() as conn:
        # Batch select existing job IDs to check what already exists
        placeholders = ",".join("?" for _ in job_ids)
        existing_rows = conn.execute(
            f"SELECT job_id FROM jobs WHERE job_id IN ({placeholders})", job_ids
        ).fetchall()
        existing_set = {r["job_id"] for r in existing_rows}
        
        for job in jobs:
            if job["job_id"] not in existing_set:
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


def last_scrape_time() -> str | None:
    """Return the run_at timestamp of the most recent successful scrape, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT run_at FROM scrape_runs WHERE status = 'ok' ORDER BY run_at DESC LIMIT 1"
        ).fetchone()
    return row["run_at"] if row else None


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


def jobs_needing_enrichment(limit: int | None = None,
                            reenrich: bool = False) -> list[dict]:
    """Return jobs to enrich (newest first), as {job_id, url} dicts.

    Default: jobs never enriched (`enriched_at IS NULL`) — the daily-scrape case.
    reenrich=True: jobs missing `date_posted`, i.e. enriched before the pipeline
    captured posting date / baseSalary — used by the one-off backfill `--all`.
    """
    predicate = "date_posted IS NULL" if reenrich else "enriched_at IS NULL"
    sql = f"SELECT job_id, url FROM jobs WHERE {predicate} ORDER BY first_seen DESC"
    if limit is not None:
        sql += " LIMIT ?"
    with get_connection() as conn:
        rows = conn.execute(sql, (limit,) if limit is not None else ()).fetchall()
    return [dict(r) for r in rows]


def update_enrichment(job_id: str, data: dict[str, Any]) -> None:
    """Write enrichment fields for one job and stamp enriched_at.

    Enriched-only fields use COALESCE(new, existing) so a partial parse never
    wipes a populated field. Salary uses COALESCE(existing, new) — JSON-LD only
    *fills gaps* and never overwrites a value already parsed from the RSS feed.
    """
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE jobs SET
                closing_date  = COALESCE(?, closing_date),
                contract_type = COALESCE(?, contract_type),
                hours         = COALESCE(?, hours),
                location      = COALESCE(?, location),
                region        = COALESCE(?, region),
                date_posted   = COALESCE(?, date_posted),
                salary_min    = COALESCE(salary_min, ?),
                salary_max    = COALESCE(salary_max, ?),
                enriched_at   = ?
            WHERE job_id = ?
            """,
            (data.get("closing_date"), data.get("contract_type"), data.get("hours"),
             data.get("location"), data.get("region"), data.get("date_posted"),
             data.get("salary_min"), data.get("salary_max"), _now(), job_id),
        )
        conn.commit()
