"""Institution-level queries: top recruiters, spikes, weekly trends."""

from db.schema import get_connection

_CLEAN_TS = "substr(replace(first_seen, 'T', ' '), 1, 19)"


def top_institutions(days: int = 30, limit: int = 20) -> list[dict]:
    """Institutions with the most new postings in the last N days.

    Returns rows of {institution, job_count, categories, avg_salary_min}.
    """
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
    """Weekly posting count for a single institution.

    Returns rows of {week, job_count}.
    """
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
    """Cross-tab of institution x category counts in the last N days.

    Returns rows of {institution, category, job_count}, useful for spotting
    which role types a given institution is focused on.
    """
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
    """Institutions that have posted >= threshold jobs in the last N days.

    Threshold defaults to 3 here; the alert module applies the config value.
    Returns rows of {institution, job_count, categories, category_list}.
    """
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
    """Average salary range per institution (institutions with >= min_jobs postings).

    Returns rows of {institution, job_count, avg_salary_min, avg_salary_max}.
    """
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
