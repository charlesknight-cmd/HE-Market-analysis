"""Time-series trend queries against the jobs database."""

import re
from collections import Counter

from db.schema import get_connection

# SQLite helper: strip timezone suffix so strftime works on both old and new timestamps
_CLEAN_TS      = "substr(replace(first_seen, 'T', ' '), 1, 19)"
_CLEAN_LAST_TS = "substr(replace(last_seen,  'T', ' '), 1, 19)"

_STOPWORDS = {
    'a', 'an', 'the', 'of', 'in', 'for', 'and', 'at', 'to', 'with', 'on',
    'by', 'or', 'is', 'are', 'be', 'from', 'as', 'into', 'its', 'this',
    'that', 'which', 'has', 'have', 'had', 'will', 'would', 'our', 'your',
    'their', 'we', 'you', 'he', 'she', 'it', 'they', 'amp', 'new', 'fixed',
    'term', 'based', 'part', 'time', 'full',
}


def category_weekly_counts(weeks: int = 12) -> list[dict]:
    """New job postings per category per ISO week for the last N weeks."""
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', {_CLEAN_TS}) AS week,
                category,
                COUNT(*)                          AS job_count
            FROM jobs
            WHERE {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY week, category
            ORDER BY week, category
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def category_share_over_time(weeks: int = 16) -> list[dict]:
    """Weekly category share as a percentage of all postings that week."""
    rows = category_weekly_counts(weeks=weeks)
    if not rows:
        return []
    week_totals: dict[str, int] = {}
    for r in rows:
        week_totals[r["week"]] = week_totals.get(r["week"], 0) + r["job_count"]
    result = []
    for r in rows:
        total = week_totals[r["week"]]
        result.append({
            **r,
            "share_pct": round(r["job_count"] / total * 100, 1) if total else 0,
        })
    return result


def category_growth_wow() -> list[dict]:
    """Week-on-week percentage change per category."""
    rows = category_weekly_counts(weeks=4)
    if not rows:
        return []
    by_cat: dict[str, dict[str, int]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], {})[r["week"]] = r["job_count"]
    all_weeks = sorted({r["week"] for r in rows})
    if len(all_weeks) < 2:
        return []
    this_week = all_weeks[-1]
    last_week = all_weeks[-2]
    results = []
    for cat, week_counts in by_cat.items():
        this_n = week_counts.get(this_week, 0)
        last_n = week_counts.get(last_week, 0)
        change_pct = round((this_n - last_n) / last_n * 100, 1) if last_n > 0 else None
        results.append({
            "category":   cat,
            "this_week":  this_n,
            "last_week":  last_n,
            "change_pct": change_pct,
        })
    return sorted(results, key=lambda x: (x["change_pct"] or 0), reverse=True)


def monthly_postings(months: int = 12) -> list[dict]:
    """New postings per month per category — for seasonal pattern analysis."""
    days = months * 31
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-%m', {_CLEAN_TS}) AS month,
                category,
                COUNT(*)                        AS job_count
            FROM jobs
            WHERE {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY month, category
            ORDER BY month, category
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def salary_by_month(months: int = 12) -> list[dict]:
    """Average salary floor per category per month — for inflation tracking."""
    days = months * 31
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-%m', {_CLEAN_TS}) AS month,
                category,
                ROUND(AVG(salary_min), 0)       AS avg_salary_min,
                COUNT(*)                        AS n
            FROM jobs
            WHERE salary_min IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY month, category
            ORDER BY month, category
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def salary_trends_by_category(weeks: int = 12) -> list[dict]:
    """Average salary band per category per week (jobs with parsed salary)."""
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', {_CLEAN_TS}) AS week,
                category,
                ROUND(AVG(salary_min), 0)         AS avg_salary_min,
                ROUND(AVG(salary_max), 0)         AS avg_salary_max,
                COUNT(*)                          AS n
            FROM jobs
            WHERE salary_min IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY week, category
            ORDER BY week, category
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def daily_new_jobs(days: int = 30) -> list[dict]:
    """Total new job postings per day for the last N days."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                date({_CLEAN_TS}) AS day,
                COUNT(*)           AS job_count
            FROM jobs
            WHERE {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY day
            ORDER BY day
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def title_word_frequency(days: int = 90, top_n: int = 30) -> list[dict]:
    """Top words appearing in job titles over the last N days."""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT title FROM jobs WHERE {_CLEAN_TS} >= datetime('now', :offset)",
            {"offset": f"-{days} days"},
        ).fetchall()
    words: Counter = Counter()
    for (title,) in rows:
        tokens = re.findall(r"\b[a-zA-Z][a-zA-Z]+\b", title or "")
        tokens = [t.lower() for t in tokens if t.lower() not in _STOPWORDS and len(t) > 2]
        words.update(tokens)
    return [{"term": t, "count": c} for t, c in words.most_common(top_n)]


def job_longevity_distribution() -> list[dict]:
    """Distribution of how many days jobs remain visible in the RSS feed.

    'days_visible' = last_seen - first_seen. Zero means seen only once.
    Note: this measures time in the RSS feed top-20, not actual close date.
    """
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                CAST(ROUND(
                    julianday({_CLEAN_LAST_TS}) -
                    julianday({_CLEAN_TS})
                ) AS INTEGER) AS days_visible,
                COUNT(*) AS job_count
            FROM jobs
            GROUP BY days_visible
            ORDER BY days_visible
            """,
        ).fetchall()
    return [dict(r) for r in rows]


def contract_type_trend(weeks: int = 12) -> list[dict]:
    """Weekly count of permanent vs fixed-term contracts."""
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', {_CLEAN_TS}) AS week,
                contract_type,
                COUNT(*) AS job_count
            FROM jobs
            WHERE contract_type IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY week, contract_type
            ORDER BY week, contract_type
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def hours_trend(weeks: int = 12) -> list[dict]:
    """Weekly count of full-time vs part-time vs flexible jobs."""
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', {_CLEAN_TS}) AS week,
                hours,
                COUNT(*) AS job_count
            FROM jobs
            WHERE hours IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY week, hours
            ORDER BY week, hours
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def overall_summary() -> dict:
    """High-level counts for a quick status overview."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        new_7d = conn.execute(
            f"SELECT COUNT(*) FROM jobs WHERE {_CLEAN_TS} >= datetime('now', '-7 days')"
        ).fetchone()[0]
        new_30d = conn.execute(
            f"SELECT COUNT(*) FROM jobs WHERE {_CLEAN_TS} >= datetime('now', '-30 days')"
        ).fetchone()[0]
        categories = conn.execute(
            "SELECT COUNT(DISTINCT category) FROM jobs"
        ).fetchone()[0]
        institutions = conn.execute(
            "SELECT COUNT(DISTINCT institution) FROM jobs WHERE institution IS NOT NULL"
        ).fetchone()[0]
    return {
        "total_jobs":   total,
        "new_7d":       new_7d,
        "new_30d":      new_30d,
        "categories":   categories,
        "institutions": institutions,
    }
