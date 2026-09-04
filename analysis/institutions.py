"""Institution-level queries: top recruiters, spikes, weekly trends."""

from collections import defaultdict

from db.schema import get_connection



def top_institutions(days: int = 30, limit: int = 20) -> list[dict]:
    """Institutions with the most new postings in the last N days."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                institution,
                COUNT(*)                         AS job_count,
                (SELECT COUNT(DISTINCT v.category) FROM jobs_by_discipline v
                 WHERE v.institution = jobs.institution
                   AND v.date_posted >= date('now', :offset)
                )                                AS categories,
                ROUND(AVG(salary_min), 0)        AS avg_salary_min
            FROM jobs
            WHERE date_posted >= date('now', :offset)
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
                strftime('%Y-W%W', date_posted) AS week,
                COUNT(*)                          AS job_count
            FROM jobs
            WHERE institution = :institution
              AND date_posted >= date('now', :offset)
              AND date_posted < date('now', '-6 days', 'weekday 1')
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
            FROM jobs_by_discipline
            WHERE date_posted >= date('now', :offset)
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
                COUNT(DISTINCT job_id)          AS job_count,
                COUNT(DISTINCT category)        AS categories,
                GROUP_CONCAT(DISTINCT category) AS category_list
            FROM jobs_by_discipline
            WHERE date_posted >= date('now', :offset)
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
              AND date_posted >= date('now', :offset)
              AND institution IS NOT NULL
            GROUP BY institution
            HAVING job_count >= :min_jobs
            ORDER BY avg_salary_min DESC
            """,
            {"offset": f"-{days} days", "min_jobs": min_jobs},
        ).fetchall()
    return [dict(r) for r in rows]


def institution_posting_distribution(days: int = 120) -> list[dict]:
    """Per-institution posting counts over the last N days (true posting date).

    Feeds the recruiter-concentration Lorenz curve, so it returns the *whole*
    distribution (every institution, no min-N gate) sorted ascending by count.
    Uses the date_posted column directly (YYYY-MM-DD, 100% filled) and drops
    null/blank institutions.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                institution,
                COUNT(*) AS job_count
            FROM jobs
            WHERE date_posted >= date('now', :offset)
              AND institution IS NOT NULL
              AND TRIM(institution) <> ''
            GROUP BY institution
            ORDER BY job_count ASC
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]
