"""Time-series trend queries against the jobs database."""

import re
import math
from collections import Counter, defaultdict

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


def seasonal_heatmap_data() -> list[dict]:
    """Return job counts grouped by calendar month number and category."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%m', {_CLEAN_TS}) AS month_num,
                category,
                COUNT(*)                    AS job_count
            FROM jobs
            GROUP BY month_num, category
            ORDER BY month_num, category
            """
        ).fetchall()
    return [dict(r) for r in rows]


def recruitment_window_trends(weeks: int = 24) -> list[dict]:
    """Return average gap in days between closing_date and first_seen over time."""
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', {_CLEAN_TS}) AS week,
                ROUND(AVG(julianday(closing_date) - julianday(COALESCE(date_posted, date({_CLEAN_TS})))), 1) AS avg_window_days,
                COUNT(*) AS job_count
            FROM jobs
            WHERE closing_date IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY week
            ORDER BY week
            """,
            {"offset": f"-{days} days"}
        ).fetchall()
    return [dict(r) for r in rows]


def market_concentration_trends(weeks: int = 24) -> list[dict]:
    """Calculate the Herfindahl-Hirschman Index (HHI) of institutions per week."""
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', {_CLEAN_TS}) AS week,
                institution,
                COUNT(*) AS job_count
            FROM jobs
            WHERE institution IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY week, institution
            ORDER BY week
            """,
            {"offset": f"-{days} days"}
        ).fetchall()

    weekly_counts = defaultdict(list)
    for r in rows:
        weekly_counts[r["week"]].append(r["job_count"])

    hhi_trends = []
    for week, counts in sorted(weekly_counts.items()):
        total = sum(counts)
        if total > 0:
            hhi = sum(((count / total) * 100) ** 2 for count in counts)
            hhi_trends.append({"week": week, "hhi": round(hhi, 1), "total_jobs": total})
    return hhi_trends


def _percentile(data: list[float], pct: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    index = pct * (len(sorted_data) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return sorted_data[int(index)]
    return sorted_data[lower] * (upper - index) + sorted_data[upper] * (index - lower)


def salary_percentile_trends(weeks: int = 24) -> list[dict]:
    """Calculate 25th, 50th, and 75th percentiles of salary floors over time."""
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', {_CLEAN_TS}) AS week,
                salary_min
            FROM jobs
            WHERE salary_min IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            ORDER BY week
            """,
            {"offset": f"-{days} days"}
        ).fetchall()

    weekly_salaries = defaultdict(list)
    for r in rows:
        weekly_salaries[r["week"]].append(r["salary_min"])

    trends = []
    for week, salaries in sorted(weekly_salaries.items()):
        if len(salaries) >= 3:
            p25 = _percentile(salaries, 0.25)
            p50 = _percentile(salaries, 0.50)
            p75 = _percentile(salaries, 0.75)
            trends.append({
                "week": week,
                "p25": round(p25, 0),
                "p50": round(p50, 0),
                "p75": round(p75, 0),
                "n": len(salaries)
            })
    return trends


def keyword_salary_premiums(days: int = 90, min_occurrences: int = 2) -> list[dict]:
    """Calculate the percentage salary premium for top keywords in job titles relative to category baseline."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT title, salary_min, category
            FROM jobs
            WHERE salary_min IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            """,
            {"offset": f"-{days} days"}
        ).fetchall()

    cat_salaries = defaultdict(list)
    for r in rows:
        cat_salaries[r["category"]].append(r["salary_min"])

    cat_baselines = {}
    for cat, salaries in cat_salaries.items():
        cat_baselines[cat] = sum(salaries) / len(salaries)

    keyword_data = defaultdict(list)
    for r in rows:
        title = r["title"] or ""
        tokens = re.findall(r"\b[a-zA-Z][a-zA-Z]+\b", title)
        unique_tokens = {t.lower() for t in tokens if t.lower() not in _STOPWORDS and len(t) > 2}
        for token in unique_tokens:
            baseline = cat_baselines.get(r["category"], r["salary_min"])
            keyword_data[token].append((r["salary_min"], baseline))

    premiums = []
    for token, values in keyword_data.items():
        if len(values) >= min_occurrences:
            avg_premium = sum((sal / base) - 1 for sal, base in values) / len(values)
            avg_salary = sum(sal for sal, _ in values) / len(values)
            premiums.append({
                "term": token,
                "count": len(values),
                "avg_salary": round(avg_salary, 0),
                "premium_pct": round(avg_premium * 100, 1)
            })

    return sorted(premiums, key=lambda x: x["premium_pct"], reverse=True)


def salary_transparency_trend(weeks: int = 12) -> list[dict]:
    """Weekly share of postings that do NOT disclose a parseable salary."""
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', {_CLEAN_TS}) AS week,
                COUNT(*) AS total,
                SUM(CASE WHEN salary_min IS NULL THEN 1 ELSE 0 END) AS undisclosed
            FROM jobs
            WHERE {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY week
            ORDER BY week
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    result = []
    for r in rows:
        total = r["total"] or 0
        und = r["undisclosed"] or 0
        result.append({
            "week": r["week"],
            "total": total,
            "undisclosed": und,
            "undisclosed_pct": round(und / total * 100, 1) if total else 0,
        })
    return result


def salary_distribution(days: int = 90) -> list[dict]:
    """Raw salary floors (with category) for distribution / histogram analysis."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT salary_min, category
            FROM jobs
            WHERE salary_min IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


# Seniority bands, ordered most-specific first so first-match classification is correct
# (e.g. "associate professor" must be tested before the bare "professor" rule).
_SENIORITY_RULES = [
    ("Associate Prof / Reader",   r"associate professor|\breader\b"),
    ("Senior Lecturer",           r"senior lecturer|principal lecturer"),
    ("Lecturer / Assistant Prof", r"\blecturer\b|assistant professor"),
    ("Professor",                 r"\bprofessor\b|\bchair\b|\bprof\b"),
    ("Research Fellow / Postdoc", r"research fellow|post-?doctoral|\bpostdoc\b|research associate|research assistant"),
    ("PhD / Studentship",         r"\bphd\b|doctoral|studentship|graduate teaching"),
    ("Director / Head / Dean",    r"\bdirector\b|head of|\bdean\b|\bpro vice\b|\bvice-chancellor\b"),
    ("Manager / Officer",         r"\bmanager\b|\bofficer\b|\bco-?ordinator\b|\badministrator\b"),
    ("Technician / Analyst",      r"\btechnician\b|\banalyst\b|\bengineer\b|\bdeveloper\b"),
]


def _classify_seniority(title: str) -> str:
    t = (title or "").lower()
    for rank, pattern in _SENIORITY_RULES:
        if re.search(pattern, t):
            return rank
    return "Other / Unclassified"


def jobs_by_region(days: int = 90) -> list[dict]:
    """Posting counts per region (UK nation or 'International'), from enrichment."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT region, COUNT(*) AS job_count
            FROM jobs
            WHERE region IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY region
            ORDER BY job_count DESC
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def top_locations(days: int = 90, limit: int = 15) -> list[dict]:
    """Top hiring towns/cities by posting count, from enrichment."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT location, COUNT(*) AS job_count
            FROM jobs
            WHERE location IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY location
            ORDER BY job_count DESC
            LIMIT :lim
            """,
            {"offset": f"-{days} days", "lim": limit},
        ).fetchall()
    return [dict(r) for r in rows]


def seniority_breakdown(days: int = 365) -> list[dict]:
    """Classify job titles into seniority bands; return count + median floor per band."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT title, salary_min
            FROM jobs
            WHERE {_CLEAN_TS} >= datetime('now', :offset)
            """,
            {"offset": f"-{days} days"},
        ).fetchall()

    bands: dict[str, dict] = defaultdict(lambda: {"count": 0, "salaries": []})
    for r in rows:
        band = bands[_classify_seniority(r["title"])]
        band["count"] += 1
        if r["salary_min"] is not None:
            band["salaries"].append(r["salary_min"])

    result = []
    for rank, data in bands.items():
        sals = data["salaries"]
        result.append({
            "rank": rank,
            "count": data["count"],
            "median_salary": round(_percentile(sals, 0.5), 0) if sals else None,
            "n_with_salary": len(sals),
        })
    return sorted(result, key=lambda x: x["count"], reverse=True)
