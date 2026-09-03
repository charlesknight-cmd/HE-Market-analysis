"""Time-series trend queries against the jobs database."""

import re
import math
from collections import Counter, defaultdict

from config import LEGACY_JOB_TYPE_SLUGS
from db.schema import get_connection

# SQLite helper: strip timezone suffix so strftime works on both old and new timestamps
_CLEAN_TS      = "substr(replace(first_seen, 'T', ' '), 1, 19)"
_CLEAN_LAST_TS = "substr(replace(last_seen,  'T', ' '), 1, 19)"

# Discipline-level queries read from the views in db/schema.py rather than the
# jobs table: `jobs_by_discipline` has one row per job x academic discipline
# (so a job tagged with three disciplines counts under each), and
# `jobs_primary_discipline` has exactly one row per job labelled with its
# first-listed discipline (for per-job distributions that must not double count).
# `jobs.category` alone only records the facet a job was first scraped under.

_STOPWORDS = {
    'a', 'an', 'the', 'of', 'in', 'for', 'and', 'at', 'to', 'with', 'on',
    'by', 'or', 'is', 'are', 'be', 'from', 'as', 'into', 'its', 'this',
    'that', 'which', 'has', 'have', 'had', 'will', 'would', 'our', 'your',
    'their', 'we', 'you', 'he', 'she', 'it', 'they', 'amp', 'new', 'fixed',
    'term', 'based', 'part', 'time', 'full',
    # Geographic / institutional tokens — not role descriptors, so they muddy the
    # "title keyword" framing of the word-frequency and salary-premium charts
    # (e.g. "london" reading as a high-premium keyword is London weighting, not a
    # role). Filtered from both since both treat tokens as role signals.
    'london', 'uk', 'united', 'kingdom', 'university', 'college', 'school',
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
            FROM jobs_by_discipline
            WHERE {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY week, category
            ORDER BY week, category
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def category_share_over_time(weeks: int = 16) -> list[dict]:
    """Weekly category share as a percentage of all discipline tags that week.

    A job tagged with several disciplines contributes to each, so the
    denominator is the number of tags, not jobs - shares still sum to 100.
    """
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
            FROM jobs_by_discipline
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
            FROM jobs_by_discipline
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
            FROM jobs_by_discipline
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


# --- Conservative singular/plural folding -------------------------------------
# Safety model: a plural is folded into its singular ONLY when that singular is
# ALSO an attested key in the same aggregated data (never invent a stem). Two
# extra guards make the must-not-mangle words impossible to collapse even if a
# coincidental shorter token exists:
#   1. suffix guard  -> -ss/-us/-is/-sis/-ics/-ous (business, campus, analysis,
#                       physics/mathematics/economics, status...)
#   2. word blocklist -> irregular Greek/Latin plurals and lexicalised -s words
#                       (news, studies, species, series, analyses, theses,
#                       crises, bases, indices, criteria, data, media...).
# NOTE: do NOT add a blanket "-ses" suffix guard — it would also block the
# regular plurals processes->process, classes->class, buses->bus. The irregular
# -ses words are covered by _NEVER_DEPLURAL_WORDS instead.

_NEVER_DEPLURAL_SUFFIXES = (
    "ss",   # business, access, address, class, process (as a singular)
    "us",   # campus, status, bonus, focus, syllabus
    "is",   # basis, axis, thesis (singular)
    "sis",  # analysis, diagnosis, emphasis, synthesis
    "ics",  # physics, mathematics, economics, statistics, ethics
    "ous",  # adjectival tail, never a plural
)

_NEVER_DEPLURAL_WORDS = {
    # lexicalised -s singulars / mass nouns
    "news", "studies", "species", "series", "lens", "bias", "kudos",
    # irregular Greek/Latin plurals (-ses, -es, -ices, etc.)
    "analyses", "theses", "diagnoses", "bases", "crises", "axes",
    "indices", "matrices", "criteria", "phenomena", "data", "media",
}


def _singular_candidates(word: str) -> list:
    """Plausible singular forms of a lowercased plural-looking token.

    Returns [] when the token must NEVER be de-pluralised. Forms are only
    candidates; a merge happens in merge_plural_variants and only if a
    candidate is itself an attested key.
    """
    if not word.endswith("s"):
        return []
    if word in _NEVER_DEPLURAL_WORDS:
        return []
    for suf in _NEVER_DEPLURAL_SUFFIXES:
        if word.endswith(suf):
            return []

    cands = []
    if word.endswith("ies") and len(word) > 4:    # libraries -> library
        cands.append(word[:-3] + "y")
    if word.endswith("es") and len(word) > 4:      # processes -> process, classes -> class
        cands.append(word[:-2])
    if len(word) > 3:                              # lecturers -> lecturer
        cands.append(word[:-1])

    seen, out = set(), []
    for c in cands:
        if c and c != word and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def merge_plural_variants(counts) -> dict:
    """Fold plural tokens into their singular when BOTH forms occur in `counts`.

    `counts` MUST be the FINAL aggregated token->count mapping (dict or Counter),
    never a per-title slice. A plural is merged only if its singular candidate is
    already a key, so no stem is ever invented. Processing is in sorted() order
    for determinism. Returns a new plain dict.
    """
    keys = set(counts.keys())
    merged = dict(counts)
    for word in sorted(counts.keys()):
        if word not in merged:
            continue
        for cand in _singular_candidates(word):
            if cand in keys and cand in merged:
                merged[cand] = merged.get(cand, 0) + merged.pop(word)
                break
    return merged


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
    # Fold singular/plural variants on the AGGREGATED counts (e.g. lecturer +
    # lecturers -> lecturer). Sorted (-count, term) replaces most_common so the
    # plain-dict result still ranks highest-first with a deterministic tiebreak.
    merged = merge_plural_variants(words)
    ranked = sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    return [{"term": t, "count": c} for t, c in ranked]


def job_longevity_distribution() -> list[dict]:
    """Distribution of how many days jobs remain visible in the search listings.

    'days_visible' = last_seen - first_seen. Zero means seen only once.
    Note: this measures time visible in the listings, not actual close date.
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
            "SELECT COUNT(DISTINCT category) FROM jobs_by_discipline"
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
            FROM jobs_by_discipline
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
            FROM jobs_primary_discipline
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
        # Collapse a singular+plural pair WITHIN the same title (e.g. "Lecturer and
        # Senior Lecturers") down to the singular, so this one title contributes a
        # single (salary, baseline) tuple to the merged concept rather than two —
        # the aggregate fold below would otherwise double-count it.
        unique_tokens -= {
            tok for tok in unique_tokens
            if any(c in unique_tokens for c in _singular_candidates(tok))
        }
        for token in unique_tokens:
            baseline = cat_baselines.get(r["category"], r["salary_min"])
            keyword_data[token].append((r["salary_min"], baseline))

    # Fold singular/plural variants ACROSS titles on the FINAL aggregated keys
    # (singular in one title, plural in another). Within-title pairs are already
    # collapsed above, so each title contributes at most once to a merged key; we
    # pick survivors from the per-token counts, then concatenate each folded
    # plural's (salary, baseline) tuples onto its singular survivor, keeping
    # count / avg_salary / premium_pct correct.
    token_counts = {tok: len(vals) for tok, vals in keyword_data.items()}
    survivors = set(merge_plural_variants(token_counts).keys())
    merged_data = defaultdict(list)
    for tok, vals in keyword_data.items():
        if tok in survivors:
            target = tok
        else:
            target = next((c for c in _singular_candidates(tok) if c in survivors), tok)
        merged_data[target].extend(vals)
    keyword_data = merged_data

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
            FROM jobs_primary_discipline
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


def seniority_salary_ladder(days: int = 365, min_n: int = 15) -> list[dict]:
    """Median salary floor per seniority band — the academic pay ladder.

    Where ``seniority_breakdown`` ranks bands by posting *volume* (pay hidden in
    the hover), this ranks them by *pay* and returns an IQR (p25–p75) so the
    spread within each rung is visible, not just the midpoint.

    Restricted to **full-time** roles (``hours = 'full-time'``): part-time adverts
    on jobs.ac.uk inconsistently quote either the full-time grade figure or the
    pro-rata'd actual, and there is no reliable textual signal to tell them apart
    (only ~22 rows even state an FTE fraction). Filtering to full-time is the
    honest way to compare like-for-like pay rather than fabricating a normalised
    figure that would corrupt more rows than it fixes. The catch-all
    'Other / Unclassified' band is dropped — it is not a seniority level. Bands
    with fewer than ``min_n`` salaried full-time postings are omitted as too thin
    to summarise. salary_min is already bounded to the sane band by the parsers
    (see config.SALARY_FLOOR/CEILING), so no outlier can skew a median here.

    Returns rows of {rank, median_salary, p25, p75, n} sorted by median ascending
    (lowest rung first) so the builder can draw the ladder bottom-to-top.
    """
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT title, salary_min
            FROM jobs
            WHERE salary_min IS NOT NULL
              AND hours = 'full-time'
              AND {_CLEAN_TS} >= datetime('now', :offset)
            """,
            {"offset": f"-{days} days"},
        ).fetchall()

    bands: dict[str, list] = defaultdict(list)
    for r in rows:
        rank = _classify_seniority(r["title"])
        if rank == "Other / Unclassified":
            continue
        bands[rank].append(r["salary_min"])

    result = [{
        "rank":          rank,
        "median_salary": round(_percentile(sals, 0.5), 0),
        "p25":           round(_percentile(sals, 0.25), 0),
        "p75":           round(_percentile(sals, 0.75), 0),
        "n":             len(sals),
    } for rank, sals in bands.items() if len(sals) >= min_n]
    return sorted(result, key=lambda x: x["median_salary"])


def application_window_distribution(days: int = 180) -> list[dict]:
    """Per-job application-window lengths (closing_date − date_posted) in days.

    Uses the true posting date where enrichment captured it, falling back to
    first_seen. Returns [{window_days}], filtered to a sane 0–365 day range.
    """
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT julianday(closing_date)
                   - julianday(COALESCE(date_posted, date({_CLEAN_TS}))) AS window_days
            FROM jobs
            WHERE closing_date IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [{"window_days": round(r["window_days"])}
            for r in rows if r["window_days"] is not None and 0 <= r["window_days"] <= 365]


def upcoming_deadlines(weeks_ahead: int = 8) -> list[dict]:
    """Count of currently-open jobs closing in each of the next `weeks_ahead` weeks."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT strftime('%Y-W%W', closing_date) AS week,
                   COUNT(*)                          AS job_count
            FROM jobs
            WHERE closing_date IS NOT NULL
              AND closing_date >= date('now')
              AND closing_date <= date('now', :ahead)
            GROUP BY week
            ORDER BY week
            """,
            {"ahead": f"+{weeks_ahead * 7} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def _median_salary_by(column: str, days: int, min_jobs: int) -> list[dict]:
    """Median salary floor grouped by an enriched categorical column."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {column} AS grp, salary_min
            FROM jobs
            WHERE {column} IS NOT NULL
              AND salary_min IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        buckets[r["grp"]].append(r["salary_min"])
    result = [
        {"group": grp, "median_salary": round(_percentile(sals, 0.5), 0), "n": len(sals)}
        for grp, sals in buckets.items() if len(sals) >= min_jobs
    ]
    return sorted(result, key=lambda x: x["median_salary"], reverse=True)


def region_category_matrix(days: int = 180) -> list[dict]:
    """Posting counts per region × category — fuels the concentration heatmap."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT region, category, COUNT(*) AS job_count
            FROM jobs_by_discipline
            WHERE region IS NOT NULL
              AND {_CLEAN_TS} >= datetime('now', :offset)
            GROUP BY region, category
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def salary_by_region(days: int = 180, min_jobs: int = 3) -> list[dict]:
    """Median salary floor per region (UK nation / International)."""
    return _median_salary_by("region", days, min_jobs)


def salary_by_contract_type(days: int = 180, min_jobs: int = 3) -> list[dict]:
    """Median salary floor for permanent vs fixed-term roles."""
    return _median_salary_by("contract_type", days, min_jobs)


def daily_postings_trend(days: int = 120) -> list[dict]:
    """TRUE daily posting volume over the last N days, by date_posted.

    Counts postings grouped by their real publication date (the date_posted
    column, YYYY-MM-DD and 100%% filled), not by when we first saw them in the
    listings. This is the true-posting-date analogue of ``daily_new_jobs``,
    which keys off first_seen. date_posted needs no _CLEAN_TS wrapper.

    Returns rows of {day, job_count}; days with no postings are simply absent
    here — the builder reindexes onto a contiguous date range and fills gaps.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                date_posted AS day,
                COUNT(*)    AS job_count
            FROM jobs
            WHERE date_posted IS NOT NULL
              AND date_posted >= date('now', :offset)
            GROUP BY date_posted
            ORDER BY date_posted
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def postings_by_weekday(days: int = 120) -> list[dict]:
    """Posting counts grouped by day of week over the last N days.

    Uses the TRUE posting date (date_posted, 100% filled, no _CLEAN_TS needed).
    `dow` follows SQLite's strftime('%w') convention: 0=Sunday .. 6=Saturday.
    Weekdays with no postings simply don't appear here — the builder pads the
    missing days to zero so all seven always render.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                CAST(strftime('%w', date_posted) AS INTEGER) AS dow,
                COUNT(*)                                      AS job_count
            FROM jobs
            WHERE date_posted IS NOT NULL
              AND date_posted >= date('now', :offset)
            GROUP BY dow
            ORDER BY dow
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def salary_disclosure_by_group(days: int = 120) -> list[dict]:
    """Salary-transparency gap per discipline AND per region (TRUE posting-date window).

    For postings whose ``date_posted`` falls in the last ``days`` days, count
    per group how many state no parseable salary. "Undisclosed" is strictly
    ``salary_min IS NULL`` — this is the clean signal and is immune to the ~82%
    salary fill rate (a NULL means we genuinely could not parse a salary). The
    separate <£12k hourly-rate contamination is a *pay*-chart concern and is
    deliberately NOT folded in here.

    Two dimensions are returned in one pass, tagged by ``dim``:
      - ``dim='discipline'`` — grouped by the ``category`` slug
      - ``dim='region'`` — grouped by ``region`` (UK nation / International),
        dropping blank regions and the unhelpful 'UK (unspecified)' bucket.

    Returns rows of {grp, dim, n, undisclosed, undisclosed_pct}. The min-N
    filter is applied in the builder so callers can see raw group sizes here.
    date_posted is YYYY-MM-DD and 100% filled, so it needs no _CLEAN_TS wrapper.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                category AS grp,
                'discipline' AS dim,
                COUNT(*) AS n,
                SUM(CASE WHEN salary_min IS NULL THEN 1 ELSE 0 END) AS undisclosed
            FROM jobs_by_discipline
            WHERE date_posted >= date('now', :offset)
              AND category IS NOT NULL
              AND category != ''
            GROUP BY category
            UNION ALL
            SELECT
                region AS grp,
                'region' AS dim,
                COUNT(*) AS n,
                SUM(CASE WHEN salary_min IS NULL THEN 1 ELSE 0 END) AS undisclosed
            FROM jobs
            WHERE date_posted >= date('now', :offset)
              AND region IS NOT NULL
              AND region != ''
              AND region != 'UK (unspecified)'
            GROUP BY region
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    result = []
    for r in rows:
        n = r["n"] or 0
        und = r["undisclosed"] or 0
        result.append({
            "grp": r["grp"],
            "dim": r["dim"],
            "n": n,
            "undisclosed": und,
            "undisclosed_pct": round(und / n * 100, 1) if n else 0,
        })
    return result


def intl_vs_uk_profile(days: int = 120) -> list[dict]:
    """Structural profile of International vs UK postings as SHARE (%) metrics.

    Splits rows into two sides — 'International' (region == 'International') and
    'UK' (the four nations plus 'UK (unspecified)', i.e. any non-International
    region) — then for each side computes share-based breakdowns so the ~263 vs
    ~2000 size gap can't dominate the comparison:

      * contract-type mix: % permanent and % fixed-term (of postings whose
        contract_type is known);
      * hours mix: % full-time and % part-time (of postings whose hours are
        known);
      * salary-disclosure rate: % of all postings on that side carrying a
        sane annual salary floor (salary_min NOT NULL AND >= 12000 — the £12k
        floor strips the hourly-rate contamination noted in the data caveats).

    Uses the true posting date (date_posted, 100% filled) for the window so it
    needs no _CLEAN_TS wrapper. Returns one dict per side; NEVER returns any
    International median-£ value (International salaries are non-GBP, so a £
    figure would be meaningless — only the disclosure *rate* is reported).
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                CASE WHEN region = 'International' THEN 'International' ELSE 'UK' END
                                                                        AS side,
                COUNT(*)                                                AS total,
                SUM(CASE WHEN contract_type IS NOT NULL THEN 1 ELSE 0 END)
                                                                        AS contract_known,
                SUM(CASE WHEN contract_type = 'permanent'  THEN 1 ELSE 0 END)
                                                                        AS permanent,
                SUM(CASE WHEN contract_type = 'fixed-term' THEN 1 ELSE 0 END)
                                                                        AS fixed_term,
                SUM(CASE WHEN hours IS NOT NULL THEN 1 ELSE 0 END)      AS hours_known,
                SUM(CASE WHEN hours = 'full-time' THEN 1 ELSE 0 END)    AS full_time,
                SUM(CASE WHEN hours = 'part-time' THEN 1 ELSE 0 END)    AS part_time,
                SUM(CASE WHEN salary_min IS NOT NULL AND salary_min >= 12000
                         THEN 1 ELSE 0 END)                             AS salaried
            FROM jobs
            WHERE region IS NOT NULL
              AND date_posted >= date('now', :offset)
            GROUP BY side
            """,
            {"offset": f"-{days} days"},
        ).fetchall()

    def _pct(n: int, d: int):
        return round(n / d * 100, 1) if d else None

    result = []
    for r in rows:
        total = r["total"] or 0
        ck = r["contract_known"] or 0
        hk = r["hours_known"] or 0
        result.append({
            "side":                 r["side"],
            "total":                total,
            "pct_permanent":        _pct(r["permanent"], ck),
            "pct_fixed_term":       _pct(r["fixed_term"], ck),
            "pct_full_time":        _pct(r["full_time"], hk),
            "pct_part_time":        _pct(r["part_time"], hk),
            "pct_salary_disclosed": _pct(r["salaried"], total),
        })
    return result


def application_window_by_discipline(days: int = 180, min_n: int = 10) -> list[dict]:
    """Application-window benchmark per discipline over the posting-date window.

    window_days = closing_date − date_posted, computed from the TRUE posting date
    (date_posted is YYYY-MM-DD and 100% filled, so no _CLEAN_TS wrapper is needed)
    and clamped to a sane 0–180 day range to drop data-entry noise. For every
    discipline with at least `min_n` such jobs we return the median (plus the
    25th/75th percentiles for an IQR whisker) and the sample size; `market_median`
    is the all-discipline median, carried on each row so the builder can draw a
    single reference line without re-querying. Sorted fastest-closing first.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT job_id, category,
                   julianday(closing_date) - julianday(date_posted) AS window_days
            FROM jobs_by_discipline
            WHERE closing_date IS NOT NULL
              AND date_posted IS NOT NULL
              AND category IS NOT NULL
              AND date_posted >= date('now', :offset)
              AND (julianday(closing_date) - julianday(date_posted)) BETWEEN 0 AND 180
            """,
            {"offset": f"-{days} days"},
        ).fetchall()

    by_cat: dict[str, list] = defaultdict(list)
    per_job: dict[str, float] = {}   # a multi-discipline job counts once in the market median
    for r in rows:
        by_cat[r["category"]].append(r["window_days"])
        per_job[r["job_id"]] = r["window_days"]
    all_windows = list(per_job.values())

    if not all_windows:
        return []

    market_median = round(_percentile(all_windows, 0.5), 1)
    result = []
    for cat, windows in by_cat.items():
        if len(windows) >= min_n:
            result.append({
                "category": cat,
                "median_days": round(_percentile(windows, 0.5), 1),
                "p25": round(_percentile(windows, 0.25), 1),
                "p75": round(_percentile(windows, 0.75), 1),
                "n": len(windows),
                "market_median": market_median,
            })
    return sorted(result, key=lambda x: x["median_days"])


def contract_hours_matrix(days: int = 180) -> list[dict]:
    """Posting counts cross-tabbed by contract_type x hours — the precarity matrix.

    Whole-market grain over the true posting-date window (date_posted is 100%
    filled and needs no _CLEAN_TS wrapper). Both dimensions come from detail-page
    enrichment, so rows where either is NULL are excluded; the resulting total is
    the enriched subset the builder reports as n=...
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT contract_type,
                   hours,
                   COUNT(*) AS job_count
            FROM jobs
            WHERE contract_type IS NOT NULL
              AND hours IS NOT NULL
              AND date_posted >= date('now', :offset)
            GROUP BY contract_type, hours
            ORDER BY contract_type, hours
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def deadline_urgency_buckets() -> list[dict]:
    """Bucket currently-open jobs by how many days remain until their deadline.

    For every open job (closing_date >= today) compute days-to-close as
    julianday(closing_date) - julianday('now') and drop it into one of five
    ordered urgency bands. Returns one row per band, always all five and in
    urgency order (most urgent first), padding empty bands with zero so the
    deadline-pressure histogram draws a complete, stable axis.

    closing_date is YYYY-MM-DD and 100% filled, so it is used directly (no
    _CLEAN_TS wrapper needed).
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                CASE
                    WHEN julianday(closing_date) - julianday('now') < 4  THEN '0-3'
                    WHEN julianday(closing_date) - julianday('now') < 8  THEN '4-7'
                    WHEN julianday(closing_date) - julianday('now') < 15 THEN '8-14'
                    WHEN julianday(closing_date) - julianday('now') < 31 THEN '15-30'
                    ELSE '30+'
                END     AS bucket,
                COUNT(*) AS job_count
            FROM jobs
            WHERE closing_date IS NOT NULL
              AND closing_date >= date('now')
            GROUP BY bucket
            """
        ).fetchall()
    counts = {r["bucket"]: r["job_count"] for r in rows}
    order = ["0-3", "4-7", "8-14", "15-30", "30+"]
    return [{"bucket": b, "job_count": counts.get(b, 0)} for b in order]


def most_reposted_roles(days: int = 180, limit: int = 15,
                        min_reposts: int = 3) -> list[dict]:
    """Roles re-advertised most often — a hard-to-fill / rolling-recruitment signal.

    A "role" is an exact (title, institution) pair; each row in `jobs` is a
    distinct advert (unique job_id), so COUNT(*) is the number of separate times
    that role was advertised over the true-posting-date window. A role posted
    many times is either genuinely hard to fill or run as rolling recruitment —
    either way a market signal no other chart surfaces. Alongside the repost
    count we carry the mean application window (closing_date − date_posted, in
    days) so the builder can show how long each advert typically stays open;
    AVG skips adverts missing either date. Exact-title matching is deliberately
    conservative — it under-counts near-duplicates ("… (Fixed Term)") rather than
    risk merging distinct roles. date_posted is 100%% filled (no _CLEAN_TS wrapper).

    Returns rows of {title, institution, repost_count, avg_window_days} sorted by
    repost_count descending, keeping only roles at or above `min_reposts`.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT title,
                   institution,
                   COUNT(*) AS repost_count,
                   AVG(julianday(closing_date) - julianday(date_posted))
                                                       AS avg_window_days
            FROM jobs
            WHERE date_posted IS NOT NULL
              AND title IS NOT NULL
              AND institution IS NOT NULL
              AND date_posted >= date('now', :offset)
            GROUP BY title, institution
            HAVING repost_count >= :min_reposts
            ORDER BY repost_count DESC, title ASC
            LIMIT :limit
            """,
            {"offset": f"-{days} days", "min_reposts": min_reposts, "limit": limit},
        ).fetchall()
    return [{
        "title":           r["title"],
        "institution":     r["institution"],
        "repost_count":    r["repost_count"],
        "avg_window_days": round(r["avg_window_days"], 1)
                           if r["avg_window_days"] is not None else None,
    } for r in rows]


def international_destinations(days: int = 180, limit: int = 15) -> list[dict]:
    """Top hiring cities among International postings, over the posting-date window.

    `region == 'International'` collapses everywhere-outside-the-UK into one
    bucket on the map; this breaks that bucket back out by `location` (the
    town/city parsed from each detail page) so the real geography — Dublin, Hong
    Kong, Singapore, … — is visible. Rows without a location are dropped.
    date_posted is 100%% filled, so it needs no _CLEAN_TS wrapper.

    Returns rows of {location, job_count} sorted by count descending.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT location, COUNT(*) AS job_count
            FROM jobs
            WHERE region = 'International'
              AND location IS NOT NULL
              AND location != ''
              AND date_posted >= date('now', :offset)
            GROUP BY location
            ORDER BY job_count DESC, location ASC
            LIMIT :limit
            """,
            {"offset": f"-{days} days", "limit": limit},
        ).fetchall()
    return [dict(r) for r in rows]


def scraper_health(hours: int = 24) -> dict:
    """Operational health of the scraper from the scrape_runs log.

    The scraper writes one scrape_runs row per discipline per run (≈21 rows a
    run, runs hourly), so this summarises the last `hours` of that log into a
    compact status the dashboard can surface for trust and breakage-spotting:
    when we last ran, whether it succeeded, how many *new* jobs landed in the
    window, and the most recent error (if any) so a silent failure is visible
    rather than looking like a genuinely quiet market.

    run_at is stored as a plain UTC 'YYYY-MM-DD HH:MM:SS' string, so it compares
    directly against datetime('now'). Returns a dict; `last_run_at`/`last_status`
    are None when the log is empty.
    """
    with get_connection() as conn:
        last = conn.execute(
            "SELECT run_at, status FROM scrape_runs ORDER BY run_at DESC LIMIT 1"
        ).fetchone()
        window = conn.execute(
            """
            SELECT COUNT(*)                                        AS runs,
                   SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors,
                   COALESCE(SUM(jobs_new), 0)                      AS new_jobs
            FROM scrape_runs
            WHERE run_at >= datetime('now', :offset)
            """,
            {"offset": f"-{hours} hours"},
        ).fetchone()
        last_error = conn.execute(
            """
            SELECT run_at, category, error
            FROM scrape_runs
            WHERE status = 'error' AND error IS NOT NULL
            ORDER BY run_at DESC LIMIT 1
            """
        ).fetchone()
    return {
        "last_run_at":  last["run_at"] if last else None,
        "last_status":  last["status"] if last else None,
        "window_hours": hours,
        "runs":         window["runs"] or 0,
        "errors":       window["errors"] or 0,
        "new_jobs":     window["new_jobs"] or 0,
        "last_error":   dict(last_error) if last_error else None,
    }


# --- Recruitment mix: research vs lecturer posts, and the precarity it implies ---

# Title keywords that mark a research post vs a lecturer post (any grade).
_RESEARCH_TITLE_RE = re.compile(r"research (?:fellow|associate|assistant)|postdoc", re.IGNORECASE)
_LECTURER_TITLE_RE = re.compile(r"lecturer", re.IGNORECASE)

# A discipline whose research-posts-per-lecturer-post ratio sits inside this band
# is "balanced" — neither research- nor teaching-heavy — so a ratio near 1.0 is
# never forced to a side.
BALANCED_BAND = (0.8, 1.25)


def role_flags(title: str | None) -> tuple[bool, bool]:
    """(is_research_post, is_lecturer_post) from a job title."""
    t = title or ""
    return bool(_RESEARCH_TITLE_RE.search(t)), bool(_LECTURER_TITLE_RE.search(t))


def mix_label(res_per_lec: float | None) -> str:
    """'research' | 'balanced' | 'teaching' from the research-posts-per-lecturer-post ratio.

    None (no lecturer posts advertised) reads as teaching-heavy only in the
    degenerate no-research case; with any research posts it's research-heavy.
    """
    if res_per_lec is None:
        return "teaching"
    lo, hi = BALANCED_BAND
    if res_per_lec > hi:
        return "research"
    if res_per_lec < lo:
        return "teaching"
    return "balanced"


def recruitment_mix_by_discipline(days: int = 180, min_n: int = 40) -> list[dict]:
    """Per-discipline fixed-term share alongside its research:lecturer recruitment mix.

    Over the true-posting-date window, for each academic discipline (via
    `jobs_by_discipline`, so a multi-discipline advert counts under each) count
    research posts and lecturer posts from titles, and the fixed-term share of
    adverts stating a contract type. Disciplines with fewer than `min_n` such
    contracted adverts are dropped, as are legacy job-type slugs. `market_pct`
    (the all-adverts fixed-term share, counting each job once) is carried on
    every row so the builder can draw one reference line.

    Returns rows of {category, n, fixed_term, fixed_term_pct, research, lecturer,
    res_per_lec (None if no lecturer posts), mix, market_pct}, sorted ascending
    by fixed_term_pct.
    """
    offset = f"-{days} days"
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT category, title, contract_type
            FROM jobs_by_discipline
            WHERE date_posted >= date('now', :offset)
              AND category IS NOT NULL
            """,
            {"offset": offset},
        ).fetchall()
        contracted, fixed_all = conn.execute(
            """
            SELECT SUM(contract_type IN ('permanent', 'fixed-term')),
                   SUM(contract_type = 'fixed-term')
            FROM jobs
            WHERE date_posted >= date('now', :offset)
            """,
            {"offset": offset},
        ).fetchone()

    market_pct = round(100 * (fixed_all or 0) / contracted, 1) if contracted else 0.0
    per: dict[str, dict] = {}
    for r in rows:
        if r["category"] in LEGACY_JOB_TYPE_SLUGS:
            continue
        d = per.setdefault(r["category"], {"n": 0, "fixed_term": 0, "research": 0, "lecturer": 0})
        if r["contract_type"] in ("permanent", "fixed-term"):
            d["n"] += 1
            d["fixed_term"] += r["contract_type"] == "fixed-term"
        res, lec = role_flags(r["title"])
        d["research"] += res
        d["lecturer"] += lec

    result = []
    for cat, d in per.items():
        if d["n"] < min_n:
            continue
        ratio = round(d["research"] / d["lecturer"], 2) if d["lecturer"] else (None if not d["research"] else float("inf"))
        result.append({
            "category": cat, **d,
            "fixed_term_pct": round(100 * d["fixed_term"] / d["n"], 1),
            "res_per_lec": ratio,
            "mix": mix_label(ratio),
            "market_pct": market_pct,
        })
    return sorted(result, key=lambda x: x["fixed_term_pct"])
