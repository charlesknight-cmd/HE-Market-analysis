"""Time-series trend queries against the jobs database."""

from db.schema import get_connection

# SQLite helper: strip timezone suffix and coerce 'T' separator so strftime works.
# Stored timestamps may be "2026-05-26T15:18:05+00:00" (old) or "2026-05-26 15:18:05" (new).
_CLEAN_TS = "substr(replace(first_seen, 'T', ' '), 1, 19)"


def category_weekly_counts(weeks: int = 12) -> list[dict]:
    """New job postings per category per ISO week for the last N weeks.

    Returns rows of {week, category, job_count}, ordered oldest-first.
    """
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


def category_growth_wow() -> list[dict]:
    """Week-on-week percentage change per category.

    Compares the current (most recent complete) week against the previous week.
    Returns rows of {category, this_week, last_week, change_pct}.
    Change_pct is None when there is no previous-week data.
    """
    rows = category_weekly_counts(weeks=4)
    if not rows:
        return []

    # Build {category: {week: count}}
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
        if last_n > 0:
            change_pct = round((this_n - last_n) / last_n * 100, 1)
        else:
            change_pct = None
        results.append(
            {
                "category":   cat,
                "this_week":  this_n,
                "last_week":  last_n,
                "change_pct": change_pct,
            }
        )

    return sorted(results, key=lambda x: (x["change_pct"] or 0), reverse=True)


def salary_trends_by_category(weeks: int = 12) -> list[dict]:
    """Average salary band per category per week (only jobs with parsed salary).

    Returns rows of {week, category, avg_salary_min, avg_salary_max, n}.
    """
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
    """Total new job postings per day for the last N days.

    Returns rows of {day, job_count}, oldest-first.
    """
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
        "total_jobs":    total,
        "new_7d":        new_7d,
        "new_30d":       new_30d,
        "categories":    categories,
        "institutions":  institutions,
    }
