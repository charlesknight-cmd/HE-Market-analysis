import sqlite3
from datetime import datetime, timezone
from typing import Any

from config import DISCIPLINES
from db.schema import get_connection


def _now() -> str:
    # Store as plain UTC string — SQLite's strftime can't parse the +00:00 suffix
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# Keys the parameterised INSERTs bind by name. Guarantees they exist so a job
# dict from any source can be upserted without a KeyError.
_LISTING_DEFAULTS = {"location": None, "region": None, "date_posted": None}


def _with_listing_defaults(job: dict[str, Any]) -> dict[str, Any]:
    return {**_LISTING_DEFAULTS, **job}


# Authority order for job_disciplines.source: a detail-page parse beats a
# redirect-URL recovery, which beats a listing-scan tag. The upsert never lets a
# lower-authority write downgrade `source`, but always bumps last_seen.
_DISCIPLINE_UPSERT = """
    INSERT INTO job_disciplines
        (job_id, facet, slug, name, parent_slug, source, position, first_seen, last_seen)
    VALUES
        (:job_id, :facet, :slug, :name, :parent_slug, :source, :position, :now, :now)
    ON CONFLICT(job_id, facet, slug) DO UPDATE SET
        last_seen   = excluded.last_seen,
        name        = COALESCE(excluded.name, name),
        parent_slug = COALESCE(excluded.parent_slug, parent_slug),
        position    = COALESCE(excluded.position, position),
        source      = CASE
                          WHEN excluded.source = 'detail' OR source = 'detail' THEN 'detail'
                          WHEN excluded.source = 'redirect' OR source = 'redirect' THEN 'redirect'
                          ELSE source
                      END
"""


def upsert_disciplines(conn: sqlite3.Connection, job_id: str,
                       entries: list[dict[str, Any]], source: str,
                       now: str | None = None) -> int:
    """Upsert subject-area tags for one job. Returns the number of rows written.

    `entries` are {facet, slug, name?, parent_slug?, position?} dicts as produced
    by scraper.detail.parse_subject_areas / parse_redirect_disciplines. Rows are
    keyed on (job_id, facet, slug); re-seeing a tag bumps last_seen and can only
    raise `source` authority (listing < redirect < detail), never lower it.
    """
    now = now or _now()
    n = 0
    for e in entries:
        if not e.get("slug") or not e.get("facet"):
            continue
        conn.execute(_DISCIPLINE_UPSERT, {
            "job_id": job_id, "facet": e["facet"], "slug": e["slug"],
            "name": e.get("name"), "parent_slug": e.get("parent_slug"),
            "source": source, "position": e.get("position"), "now": now,
        })
        n += 1
    return n


def _listing_discipline(job: dict[str, Any]) -> list[dict[str, Any]]:
    """The academic-discipline tag implied by the facet a listing was scraped under."""
    slug = job.get("category")
    if slug not in DISCIPLINES:      # legacy job-type slug or unknown - not a discipline
        return []
    return [{"facet": "academic", "slug": slug, "name": DISCIPLINES[slug]}]


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
             location, region, date_posted, category, url, first_seen, last_seen)
        VALUES
            (:job_id, :title, :institution, :department, :salary_raw,
             :salary_min, :salary_max, :closing_date, :contract_type, :hours,
             :location, :region, :date_posted, :category, :url, :now, :now)
        ON CONFLICT(job_id) DO UPDATE SET
            last_seen     = excluded.last_seen,
            closing_date  = COALESCE(excluded.closing_date,  closing_date),
            contract_type = COALESCE(excluded.contract_type, contract_type),
            hours         = COALESCE(excluded.hours,         hours),
            location      = COALESCE(location, excluded.location),
            region        = COALESCE(region,   excluded.region),
            date_posted   = COALESCE(date_posted, excluded.date_posted),
            salary_raw    = COALESCE(salary_raw, excluded.salary_raw),
            salary_min    = COALESCE(salary_min, excluded.salary_min),
            salary_max    = COALESCE(salary_max, excluded.salary_max)
        """,
        {**_with_listing_defaults(job), "now": now},
    )
    upsert_disciplines(conn, job["job_id"], _listing_discipline(job), "listing", now)
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
                         location, region, date_posted, category, url, first_seen, last_seen)
                    VALUES
                        (:job_id, :title, :institution, :department, :salary_raw,
                         :salary_min, :salary_max, :closing_date, :contract_type, :hours,
                         :location, :region, :date_posted, :category, :url, :now, :now)
                    """,
                    {**_with_listing_defaults(job), "now": now},
                )
                new_count += 1
            else:
                # Fill-if-empty for fields the listing now supplies, so jobs first
                # seen before this column existed get backfilled without clobbering
                # anything an enrichment pass already wrote.
                conn.execute(
                    """
                    UPDATE jobs SET
                        last_seen     = ?,
                        closing_date  = COALESCE(?, closing_date),
                        contract_type = COALESCE(?, contract_type),
                        hours         = COALESCE(?, hours),
                        location      = COALESCE(location, ?),
                        region        = COALESCE(region, ?),
                        date_posted   = COALESCE(date_posted, ?),
                        salary_raw    = COALESCE(salary_raw, ?),
                        salary_min    = COALESCE(salary_min, ?),
                        salary_max    = COALESCE(salary_max, ?)
                    WHERE job_id = ?
                    """,
                    (now,
                     job.get("closing_date"), job.get("contract_type"), job.get("hours"),
                     job.get("location"), job.get("region"), job.get("date_posted"),
                     job.get("salary_raw"), job.get("salary_min"), job.get("salary_max"),
                     job["job_id"]),
                )
                updated_count += 1
            # Every scan a job turns up in is one discipline it's tagged with -
            # record it regardless of whether the row was new, so a job seen
            # under several facets accrues all of them (jobs.category keeps only
            # the first).
            upsert_disciplines(conn, job["job_id"], _listing_discipline(job), "listing", now)
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


def existing_job_ids() -> set[str]:
    """Return every job_id already stored — used to stop paginating early."""
    with get_connection() as conn:
        rows = conn.execute("SELECT job_id FROM jobs").fetchall()
    return {r["job_id"] for r in rows}


def last_scrape_time() -> str | None:
    """Return the run_at timestamp of the most recent successful scrape, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT run_at FROM scrape_runs WHERE status = 'ok' ORDER BY run_at DESC LIMIT 1"
        ).fetchone()
    return row["run_at"] if row else None


# Comma-separated academic-discipline slugs for a job, in detail-page order,
# falling back to the scraped `category` when nothing has been recorded yet.
_DISCIPLINES_EXPR = """
    COALESCE(
        (SELECT GROUP_CONCAT(slug) FROM (
            SELECT d.slug FROM job_disciplines d
            WHERE d.job_id = j.job_id AND d.facet = 'academic'
            ORDER BY d.position IS NULL, d.position, d.slug)),
        j.category
    )
"""


def get_all_jobs() -> list[dict]:
    """Every job row, plus `disciplines`: all its academic-discipline slugs, comma-joined."""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT j.*, {_DISCIPLINES_EXPR} AS disciplines FROM jobs j ORDER BY first_seen DESC"
        ).fetchall()
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
        if data.get("disciplines") is not None:
            _write_disciplines(conn, job_id, data["disciplines"],
                               data.get("discipline_source", "detail"))
        conn.commit()


def _write_disciplines(conn: sqlite3.Connection, job_id: str,
                       entries: list[dict[str, Any]], source: str) -> None:
    now = _now()
    upsert_disciplines(conn, job_id, entries, source, now)
    # Stamp even when the page listed nothing, so the backfill doesn't refetch it.
    conn.execute("UPDATE jobs SET disciplines_at = ? WHERE job_id = ?", (now, job_id))


def set_disciplines(job_id: str, entries: list[dict[str, Any]],
                    source: str = "detail") -> None:
    """Record a job's subject areas from a detail page (or expired-job redirect) and stamp disciplines_at."""
    with get_connection() as conn:
        _write_disciplines(conn, job_id, entries, source)
        conn.commit()


def jobs_needing_disciplines(limit: int | None = None) -> list[dict]:
    """Jobs whose detail-page subject areas haven't been captured, as {job_id, url}.

    Ordered by closing date descending: live and recently-closed jobs first, since
    jobs.ac.uk keeps a detail page for roughly 45 days after closing and then only
    an expired-job redirect (which still names the disciplines, minus display
    names and sub-discipline parents).
    """
    sql = ("SELECT job_id, url FROM jobs WHERE disciplines_at IS NULL "
           "ORDER BY closing_date DESC, first_seen DESC")
    if limit is not None:
        sql += " LIMIT ?"
    with get_connection() as conn:
        rows = conn.execute(sql, (limit,) if limit is not None else ()).fetchall()
    return [dict(r) for r in rows]


def discipline_coverage() -> dict:
    """Counts for the discipline backfill: how many jobs have detail-sourced tags."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        stamped = conn.execute("SELECT COUNT(*) FROM jobs WHERE disciplines_at IS NOT NULL").fetchone()[0]
        by_source = conn.execute(
            "SELECT source, COUNT(DISTINCT job_id) FROM job_disciplines "
            "WHERE facet = 'academic' GROUP BY source"
        ).fetchall()
        multi = conn.execute(
            "SELECT COUNT(*) FROM (SELECT job_id FROM job_disciplines WHERE facet = 'academic' "
            "GROUP BY job_id HAVING COUNT(*) > 1)"
        ).fetchone()[0]
    return {"total_jobs": total, "stamped": stamped, "pending": total - stamped,
            "jobs_by_source": {r[0]: r[1] for r in by_source}, "multi_discipline_jobs": multi}
