"""Time-series trend queries against the jobs database."""

import re
import math
from collections import defaultdict

from config import LEGACY_JOB_TYPE_SLUGS, discipline_label
from db.schema import get_connection

# Every windowed query keys off `date_posted` (the advert's true publication
# date, YYYY-MM-DD, 100% filled) — never `first_seen`, which is when the scraper
# first saw it and carries a 1,836-advert backfill spike in the week the scraper
# went live (26 May 2026).

# Weekly series exclude the current, partial ISO week: plotting it as if complete
# makes every series end in a false drop and turns week-on-week growth negative
# on any day but Sunday. `date('now', '-6 days', 'weekday 1')` is the Monday on
# or before today (SQLite's 'weekday 1' rolls forward to the next Monday, so
# stepping back six days first makes it land on the current week's Monday).
_COMPLETE_WEEKS = "date_posted < date('now', '-6 days', 'weekday 1')"

# Retired job-type slugs (pre-June-2026 taxonomy) still ride on a few rows'
# `category`; they are not disciplines, so discipline breakdowns skip them.
_NOT_LEGACY = "category NOT IN (" + ", ".join(f"'{x}'" for x in sorted(LEGACY_JOB_TYPE_SLUGS)) + ")"

# Discipline-level queries read from the views in db/schema.py rather than the
# jobs table: `jobs_by_discipline` has one row per job x academic discipline
# (so a job tagged with three disciplines counts under each), and
# `jobs_primary_discipline` has exactly one row per job labelled with its
# first-listed discipline (for per-job distributions that must not double count).
# `jobs.category` alone only records the facet a job was first scraped under.

def category_weekly_counts(weeks: int = 52) -> list[dict]:
    """Postings per discipline per complete ISO week (true posting date).

    A multi-discipline advert counts under each discipline. The current partial
    week is excluded (see _COMPLETE_WEEKS); `weeks` bounds the history.
    """
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', date_posted) AS week,
                category,
                COUNT(*)                          AS job_count
            FROM jobs_by_discipline
            WHERE date_posted >= date('now', :offset)
              AND {_COMPLETE_WEEKS}
              AND {_NOT_LEGACY}
            GROUP BY week, category
            ORDER BY week, category
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def category_share_over_time(weeks: int = 52) -> list[dict]:
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
    """Change per discipline between the last two COMPLETE weeks."""
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


def contract_type_trend(weeks: int = 52) -> list[dict]:
    """Permanent vs fixed-term adverts per complete ISO week (true posting date)."""
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', date_posted) AS week,
                contract_type,
                COUNT(*) AS job_count
            FROM jobs
            WHERE contract_type IS NOT NULL
              AND date_posted >= date('now', :offset)
              AND {_COMPLETE_WEEKS}
            GROUP BY week, contract_type
            ORDER BY week, contract_type
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def hours_trend(weeks: int = 52) -> list[dict]:
    """Full-time / part-time / flexible adverts per complete ISO week (true posting date)."""
    days = weeks * 7
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('%Y-W%W', date_posted) AS week,
                hours,
                COUNT(*) AS job_count
            FROM jobs
            WHERE hours IS NOT NULL
              AND date_posted >= date('now', :offset)
              AND {_COMPLETE_WEEKS}
            GROUP BY week, hours
            ORDER BY week, hours
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


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


def salary_distribution(days: int = 90) -> list[dict]:
    """Raw salary floors (with category) for distribution / histogram analysis."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT salary_min, category
            FROM jobs_primary_discipline
            WHERE salary_min IS NOT NULL
              AND date_posted >= date('now', :offset)
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


# Seniority bands, ordered most-specific first so first-match classification is correct
# (e.g. "associate professor" must be tested before the bare "professor" rule).
# Second pass (Sept 2026): plurals ("Maths Lecturers"), lectureships, "SL/AP",
# teaching fellows / tutors / teachers (their own band — they are neither
# lecturers nor researchers), open-rank faculty posts, fellowships and research
# scientists, and the professional-services vocabulary that made
# "Other / Unclassified" the second-largest band.
_SENIORITY_RULES = [
    ("Associate Prof / Reader",   r"associate professor|\breader\b"),
    ("Senior Lecturer",           r"senior lecturers?|principal lecturers?|\bsl/ap\b"),
    ("Lecturer / Assistant Prof", r"\blecturers?\b|lectureship|assistant professor"),
    ("Professor",                 r"\bprofessor\b|\bchair\b|\bprof\b"),
    ("Teaching Fellow / Tutor",   r"teaching fellow|teaching associate|teaching assistant|\btutor\b|\bteacher\b|"
                                  r"\bdemonstrator\b|\binstructor\b|hourly paid teaching|graduate teaching"),
    ("Faculty (open rank)",       r"open[- ]rank|\bfaculty (?:position|member|post)|tenure[- ]track"),
    ("Research Fellow / Postdoc", r"research fellow|post-?doctoral|\bpostdoc\b|research associate|research assistant|"
                                  r"\bresearcher\b|research scientist|\bscientist\b|\bfellowship\b|\bfellow\b"),
    ("PhD / Studentship",         r"\bphd\b|\bdphil\b|doctoral|studentship"),
    ("Director / Head / Dean",    r"\bdirector\b|head of|\bdean\b|\bpro vice\b|\bvice-chancellor\b|\bprovost\b"),
    ("Manager / Officer",         r"\bmanager\b|\bofficer\b|\bco-?ordinator\b|\badministrator\b|\blead\b|"
                                  r"\bleader\b|\badvis[eo]r\b|\bconsultant\b|\bpartner\b"),
    ("Technician / Specialist",   r"\btechnician\b|\banalyst\b|\bengineer\b|\bdeveloper\b|\bnurse\b|"
                                  r"\bspecialist\b|\btechnical\b|\bpractitioner\b|\btrainer\b|\blibrarian\b|"
                                  r"\bassistant\b|\bprosector\b|\bmidwife\b|\bpharmacist\b|\bpsychologist\b|"
                                  r"\bclinician\b|\bsupport\b"),
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
              AND date_posted >= date('now', :offset)
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
              AND date_posted >= date('now', :offset)
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
            WHERE date_posted >= date('now', :offset)
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
              AND date_posted >= date('now', :offset)
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
                   - julianday(date_posted) AS window_days
            FROM jobs
            WHERE closing_date IS NOT NULL
              AND date_posted >= date('now', :offset)
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
              AND date_posted >= date('now', :offset)
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
              AND {_NOT_LEGACY}
              AND date_posted >= date('now', :offset)
            GROUP BY region, category
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    return [dict(r) for r in rows]


def salary_by_region(days: int = 180, min_jobs: int = 3) -> list[dict]:
    """Median salary floor per UK nation.

    International is excluded: those figures are foreign salaries converted at
    the day's rate with under half disclosed, so a £ median is not comparable
    (intl_vs_uk_profile compares disclosure rate instead).
    """
    return [r for r in _median_salary_by("region", days, min_jobs)
            if r["group"] not in ("International", "UK (unspecified)")]


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
            f"""
            SELECT
                category AS grp,
                'discipline' AS dim,
                COUNT(*) AS n,
                SUM(CASE WHEN salary_min IS NULL THEN 1 ELSE 0 END) AS undisclosed
            FROM jobs_by_discipline
            WHERE date_posted >= date('now', :offset)
              AND category IS NOT NULL
              AND category != ''
              AND {_NOT_LEGACY}
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
            f"""
            SELECT job_id, category,
                   julianday(closing_date) - julianday(date_posted) AS window_days
            FROM jobs_by_discipline
            WHERE closing_date IS NOT NULL
              AND date_posted IS NOT NULL
              AND category IS NOT NULL
              AND {_NOT_LEGACY}
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


# PhD studentships are training places, not employment; they are 96% fixed-term
# by nature and would inflate any fixed-term share, so precarity measures drop
# them. Matches the seniority band's PhD rule plus doctoral-student wording.
_STUDENTSHIP_RE = re.compile(
    r"\bphd\b|\bdphil\b|studentship|doctoral (?:student|researcher|candidate|scholar|training)", re.IGNORECASE)


def is_studentship(title: str | None) -> bool:
    """True if the advert is a PhD/doctoral studentship rather than a job."""
    return bool(_STUDENTSHIP_RE.search(title or ""))


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


def recruitment_mix_by_discipline(days: int = 180, min_n: int = 40,
                                  exclude_studentships: bool = True) -> list[dict]:
    """Per-discipline fixed-term share alongside its research:lecturer recruitment mix.

    Over the true-posting-date window, for each academic discipline (via
    `jobs_by_discipline`, so a multi-discipline advert counts under each) count
    research posts and lecturer posts from titles, and the fixed-term share of
    adverts stating a contract type. PhD studentships are excluded from the
    fixed-term share by default (see is_studentship) — they are not jobs and are
    fixed-term by nature. Disciplines with fewer than `min_n` contracted adverts
    are dropped, as are legacy job-type slugs. `market_pct` (the all-adverts
    fixed-term share, counting each job once, same exclusion) is carried on
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
        market_rows = conn.execute(
            """
            SELECT title, contract_type
            FROM jobs
            WHERE date_posted >= date('now', :offset)
              AND contract_type IN ('permanent', 'fixed-term')
            """,
            {"offset": offset},
        ).fetchall()

    def _counts(r) -> bool:
        return not (exclude_studentships and is_studentship(r["title"]))

    market = [r for r in market_rows if _counts(r)]
    contracted = len(market)
    fixed_all = sum(r["contract_type"] == "fixed-term" for r in market)
    market_pct = round(100 * fixed_all / contracted, 1) if contracted else 0.0
    per: dict[str, dict] = {}
    for r in rows:
        if r["category"] in LEGACY_JOB_TYPE_SLUGS:
            continue
        d = per.setdefault(r["category"], {"n": 0, "fixed_term": 0, "research": 0, "lecturer": 0})
        if r["contract_type"] in ("permanent", "fixed-term") and _counts(r):
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


# --- Headline figures, pay by discipline, sub-discipline drill-down, coverage ---

def headline_stats(days: int = 90) -> dict:
    """The numbers the Overview leads with, each stated as a level, not a trend.

    Weekly counts use the last two COMPLETE ISO weeks (true posting date) so the
    delta is week-vs-week, never partial-vs-full. Rates are over the last `days`
    days of postings. Studentships are excluded from the permanent share for the
    same reason as in recruitment_mix_by_discipline.
    """
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        weeks = conn.execute(
            f"""
            SELECT strftime('%Y-W%W', date_posted) AS week, COUNT(*) AS n
            FROM jobs
            WHERE {_COMPLETE_WEEKS}
            GROUP BY week ORDER BY week DESC LIMIT 2
            """
        ).fetchall()
        recent = conn.execute(
            """
            SELECT title, contract_type, salary_min,
                   julianday(closing_date) - julianday(date_posted) AS window_days
            FROM jobs
            WHERE date_posted >= date('now', :offset)
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
        institutions = conn.execute(
            "SELECT COUNT(DISTINCT institution) FROM jobs "
            "WHERE institution IS NOT NULL AND date_posted >= date('now', :offset)",
            {"offset": f"-{days} days"},
        ).fetchone()[0]
        disciplines = conn.execute(
            f"SELECT COUNT(DISTINCT category) FROM jobs_by_discipline WHERE {_NOT_LEGACY}"
        ).fetchone()[0]

    windows = [r["window_days"] for r in recent
               if r["window_days"] is not None and 0 <= r["window_days"] <= 180]
    contracted = [r for r in recent if r["contract_type"] in ("permanent", "fixed-term")
                  and not is_studentship(r["title"])]
    n_recent = len(recent)
    return {
        "total_jobs": total,
        "last_week": weeks[0]["n"] if weeks else 0,
        "last_week_label": weeks[0]["week"] if weeks else None,
        "prev_week": weeks[1]["n"] if len(weeks) > 1 else None,
        "median_window_days": round(_percentile(windows, 0.5)) if windows else None,
        "hidden_pay_pct": round(100 * sum(r["salary_min"] is None for r in recent) / n_recent, 1) if n_recent else None,
        "permanent_pct": round(100 * sum(r["contract_type"] == "permanent" for r in contracted) / len(contracted), 1)
                         if contracted else None,
        "institutions": institutions,
        "disciplines": disciplines,
        "window_days": days,
        "n_recent": n_recent,
    }


def salary_by_discipline(days: int = 180, min_n: int = 20) -> list[dict]:
    """Median advertised salary floor per discipline, with the p25-p75 spread.

    Full-time adverts only (part-time quote FTE and pro-rata inconsistently) over
    the true-posting-date window; a multi-discipline advert counts under each of
    its disciplines. Disciplines with fewer than `min_n` salaried full-time
    adverts are omitted. Sorted by median ascending.
    """
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT category, salary_min
            FROM jobs_by_discipline
            WHERE salary_min IS NOT NULL
              AND hours = 'full-time'
              AND {_NOT_LEGACY}
              AND date_posted >= date('now', :offset)
            """,
            {"offset": f"-{days} days"},
        ).fetchall()
    by_cat: dict[str, list] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r["salary_min"])
    result = [{
        "category": cat,
        "median_salary": round(_percentile(v, 0.5)),
        "p25": round(_percentile(v, 0.25)),
        "p75": round(_percentile(v, 0.75)),
        "n": len(v),
    } for cat, v in by_cat.items() if len(v) >= min_n]
    return sorted(result, key=lambda x: x["median_salary"])


def _tag_breakdown(where: str, params: dict, min_n: int) -> list[dict]:
    """Shared body for the sub-discipline and non-academic breakdowns."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT d.slug, d.name, j.title, j.contract_type, j.salary_min, j.hours
            FROM job_disciplines d
            JOIN jobs j ON j.job_id = d.job_id
            WHERE {where}
              AND j.date_posted >= date('now', :offset)
            """,
            params,
        ).fetchall()
    per: dict[str, dict] = {}
    for r in rows:
        d = per.setdefault(r["slug"], {"name": None, "n": 0, "contracted": 0, "fixed_term": 0, "salaries": []})
        d["name"] = d["name"] or r["name"]
        d["n"] += 1
        if r["contract_type"] in ("permanent", "fixed-term") and not is_studentship(r["title"]):
            d["contracted"] += 1
            d["fixed_term"] += r["contract_type"] == "fixed-term"
        if r["salary_min"] is not None and r["hours"] == "full-time":
            d["salaries"].append(r["salary_min"])
    result = []
    for slug, d in per.items():
        if d["n"] < min_n:
            continue
        result.append({
            "slug": slug,
            "name": d["name"] or discipline_label(slug),
            "n": d["n"],
            "fixed_term_pct": round(100 * d["fixed_term"] / d["contracted"], 1) if d["contracted"] else None,
            "n_contracted": d["contracted"],
            "median_salary": round(_percentile(d["salaries"], 0.5)) if len(d["salaries"]) >= 5 else None,
            "n_salaried": len(d["salaries"]),
        })
    return sorted(result, key=lambda x: -x["n"])


def subdiscipline_breakdown(parent_slug: str, days: int = 180, min_n: int = 5) -> list[dict]:
    """Adverts per sub-discipline within one academic discipline.

    Sub-discipline tags come from each advert's detail page (job_disciplines,
    facet 'sub', parent_slug = the discipline). For each with at least `min_n`
    adverts in the true-posting-date window: count, fixed-term share of
    contracted non-studentship adverts, and the median full-time salary floor
    (None below five salaried adverts). Sorted by count descending.
    """
    return _tag_breakdown("d.facet = 'sub' AND d.parent_slug = :parent",
                          {"parent": parent_slug, "offset": f"-{days} days"}, min_n)


def nonacademic_breakdown(days: int = 180, min_n: int = 5) -> list[dict]:
    """Adverts per non-academic (professional services) area — the jobs the
    discipline charts cannot see. Same shape as subdiscipline_breakdown."""
    return _tag_breakdown("d.facet = 'non-academic'", {"offset": f"-{days} days"}, min_n)


def attribution_counts() -> list[dict]:
    """Adverts per discipline under three attribution rules, all time.

    every_tag: counted under every academic discipline the advert carries.
    first_listed: one label per advert, the first subject on its detail page.
    first_scanned: one label per advert, the facet the scraper scanned first
    (the project's original, alphabetically biased rule). `ratio` is
    every_tag / first_listed. Legacy job-type slugs are dropped.
    """
    with get_connection() as conn:
        every = dict(conn.execute("SELECT category, COUNT(*) FROM jobs_by_discipline GROUP BY 1").fetchall())
        first = dict(conn.execute("SELECT category, COUNT(*) FROM jobs_primary_discipline GROUP BY 1").fetchall())
        scanned = dict(conn.execute("SELECT category, COUNT(*) FROM jobs GROUP BY 1").fetchall())
    rows = []
    for cat, n in every.items():
        if cat in LEGACY_JOB_TYPE_SLUGS:
            continue
        f = first.get(cat, 0)
        rows.append({"category": cat, "every_tag": n, "first_listed": f,
                     "first_scanned": scanned.get(cat, 0),
                     "ratio": round(n / f, 2) if f else None})
    return sorted(rows, key=lambda r: (r["ratio"] is None, r["ratio"] or 0))


def data_coverage() -> dict:
    """Fill rates the Data tab reports so a reader can judge each chart's footing."""
    with get_connection() as conn:
        r = conn.execute(
            """
            SELECT COUNT(*)                                   AS total,
                   SUM(enriched_at IS NOT NULL)               AS enriched,
                   SUM(contract_type IS NOT NULL)             AS contract,
                   SUM(salary_min IS NOT NULL)                AS salaried,
                   SUM(region IS NOT NULL)                    AS region,
                   SUM(disciplines_at IS NOT NULL)            AS disciplines,
                   MIN(date_posted), MAX(date_posted)
            FROM jobs
            """
        ).fetchone()
        multi = conn.execute(
            "SELECT COUNT(*) FROM (SELECT job_id FROM job_disciplines WHERE facet = 'academic' "
            "GROUP BY job_id HAVING COUNT(*) > 1)"
        ).fetchone()[0]
    total = r[0] or 0
    pct = lambda n: round(100 * (n or 0) / total, 1) if total else 0.0
    return {"total": total, "enriched_pct": pct(r[1]), "contract_pct": pct(r[2]),
            "salary_pct": pct(r[3]), "region_pct": pct(r[4]), "disciplines_pct": pct(r[5]),
            "multi_discipline_pct": pct(multi), "posted_min": r[6], "posted_max": r[7]}
