"""Institution-level queries: top recruiters, spikes, weekly trends."""

from collections import defaultdict

from db.schema import get_connection

_CLEAN_TS = "substr(replace(first_seen, 'T', ' '), 1, 19)"


def top_institutions(days: int = 30, limit: int = 20) -> list[dict]:
    """Institutions with the most new postings in the last N days."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                institution,
                COUNT(*)                         AS job_count,
                COUNT(DISTINCT category)         AS categories,
                ROUND(AVG(salary_min), 0)        AS avg_salary_min
            FROM jobs
            WHERE {_CLEAN_TS} >= datetime('now', :offset)
              AND institution IS NOT NULL
            GROUP BY institution
            ORDER BY job_count DESC
            LIMIT :limit
            """,
            {"offset": f"-{days} days", "limit": limit},
        ).fetchall()
    return [dict(r) for r in rows]


def institution_weekly_trend(institution: str, weeks: int = 12) -> list[dict]:
    """Weekly posting count for a single institution."""
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', {_CLEAN_TS}) AS week,
                COUNT(*)                          AS job_count
            FROM jobs
            WHERE institution = :institution
              AND {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY week
            ORDER BY week
            """,
            {"institution": institution, "offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def institution_category_breakdown(days: int = 30) -> list[dict]:
    """Cross-tab of institution x category counts in the last N days."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                institution,
                category,
                COUNT(*) AS job_count
            FROM jobs
            WHERE {_CLEAN_TS} >= datetime('now', :offset)
              AND institution IS NOT NULL
            GROUP BY institution, category
            ORDER BY institution, job_count DESC
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def spike_candidates(days: int = 7, threshold: int = 3) -> list[dict]:
    """Institutions that have posted >= threshold jobs in the last N days."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                institution,
                COUNT(*)                        AS job_count,
                COUNT(DISTINCT category)        AS categories,
                GROUP_CONCAT(DISTINCT category) AS category_list
            FROM jobs
            WHERE {_CLEAN_TS} >= datetime('now', :offset)
              AND institution IS NOT NULL
            GROUP BY institution
            HAVING job_count >= :threshold
            ORDER BY job_count DESC
            """,
            {"offset": f"-{days} days", "threshold": threshold},
        ).fetchall()
    return [dict(r) for r in rows]


def salary_by_institution(days: int = 90, min_jobs: int = 3) -> list[dict]:
    """Average salary range per institution (institutions with >= min_jobs postings)."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                institution,
                COUNT(*)                  AS job_count,
                ROUND(AVG(salary_min), 0) AS avg_salary_min,
                ROUND(AVG(salary_max), 0) AS avg_salary_max
            FROM jobs
            WHERE salary_min IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
              AND institution IS NOT NULL
            GROUP BY institution
            HAVING job_count >= :min_jobs
            ORDER BY avg_salary_min DESC
            """,
            {"offset": f"-{days} days", "min_jobs": min_jobs},
        ).fetchall()
    return [dict(r) for r in rows]


def new_vs_repeat_institutions(weeks: int = 12) -> list[dict]:
    """Per ISO week: institutions posting for the first time vs returning ones.

    'New' = this is the earliest week we have any job from that institution.
    'Repeat' = institution appeared in a prior week.
    Returns rows of {week, new_count, repeat_count}.
    """
    days = weeks * 7

    # First-ever posting week per institution (all time, not windowed)
    with get_connection() as conn:
        debut_rows = conn.execute(
            f"""
            SELECT
                institution,
                strftime('%Y-W%W', MIN({_CLEAN_TS})) AS debut_week
            FROM jobs
            WHERE institution IS NOT NULL
            GROUP BY institution
            """
        ).fetchall()

    debut_week = {r["institution"]: r["debut_week"] for r in debut_rows}

    # Weekly institution appearances within the lookback window
    with get_connection() as conn:
        window_rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', {_CLEAN_TS}) AS week,
                institution
            FROM jobs
            WHERE institution IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY week, institution
            ORDER BY week
            """,
            {"offset": f"-{days} days"},
        ).fetchall()

    weekly: dict[str, dict[str, int]] = defaultdict(lambda: {"new_count": 0, "repeat_count": 0})
    for r in window_rows:
        key = "new_count" if debut_week.get(r["institution"]) == r["week"] else "repeat_count"
        weekly[r["week"]][key] += 1

    return [{"week": w, **v} for w, v in sorted(weekly.items())]
