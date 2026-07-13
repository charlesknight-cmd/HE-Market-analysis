"""Smoke-test every dashboard chart builder against the live database.

For each chart: fetch its real data, build the figure, and report whether it
came back as the 'no data' placeholder, errored, or rendered with N traces.

Run with:  python scripts/chart_smoke_test.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis import trends
from analysis.institutions import (
    institution_posting_distribution, new_vs_repeat_institutions,
    salary_by_institution, top_institutions,
)
from dashboard import charts

LOOKBACK_DAYS = 30
WEEKS = LOOKBACK_DAYS // 7
MONTHS = max(1, LOOKBACK_DAYS // 30)

CASES = [
    ("daily_jobs_line", charts.daily_jobs_line, lambda: trends.daily_new_jobs(days=LOOKBACK_DAYS)),
    ("category_weekly_bar", charts.category_weekly_bar, lambda: trends.category_weekly_counts(weeks=WEEKS)),
    ("category_share_area", charts.category_share_area, lambda: trends.category_share_over_time(weeks=WEEKS)),
    ("seasonal_bar", charts.seasonal_bar, lambda: trends.monthly_postings(months=max(MONTHS, 3))),
    ("seasonal_heatmap", charts.seasonal_heatmap, trends.seasonal_heatmap_data),
    ("salary_inflation_line", charts.salary_inflation_line, lambda: trends.salary_by_month(months=max(MONTHS, 3))),
    ("salary_percentile_bands", charts.salary_percentile_bands, lambda: trends.salary_percentile_trends(weeks=WEEKS)),
    ("salary_transparency_line", charts.salary_transparency_line, lambda: trends.salary_transparency_trend(weeks=WEEKS)),
    ("contract_type_bar", charts.contract_type_bar, lambda: trends.contract_type_trend(weeks=WEEKS)),
    ("permanent_ratio_line", charts.permanent_ratio_line, lambda: trends.contract_type_trend(weeks=WEEKS)),
    ("hours_bar", charts.hours_bar, lambda: trends.hours_trend(weeks=WEEKS)),
    ("recruitment_window_line", charts.recruitment_window_line, lambda: trends.recruitment_window_trends(weeks=WEEKS)),
    ("application_window_hist", charts.application_window_hist, lambda: trends.application_window_distribution(days=LOOKBACK_DAYS)),
    ("upcoming_deadlines_bar", charts.upcoming_deadlines_bar, lambda: trends.upcoming_deadlines(weeks_ahead=8)),
    ("title_frequency_bar", charts.title_frequency_bar, lambda: trends.title_word_frequency(days=LOOKBACK_DAYS)),
    ("category_growth_bar", charts.category_growth_bar, trends.category_growth_wow),
    ("salary_box_by_category", charts.salary_box_by_category, lambda: trends.salary_trends_by_category(weeks=WEEKS)),
    ("salary_distribution_hist", charts.salary_distribution_hist, lambda: trends.salary_distribution(days=LOOKBACK_DAYS)),
    ("seniority_breakdown_bar", charts.seniority_breakdown_bar, lambda: trends.seniority_breakdown(days=365)),
    ("keyword_premium_bar", charts.keyword_premium_bar, lambda: trends.keyword_salary_premiums(days=LOOKBACK_DAYS)),
    ("top_institutions_bar", lambda rows: charts.top_institutions_bar(rows, LOOKBACK_DAYS), lambda: top_institutions(days=LOOKBACK_DAYS, limit=20)),
    ("institution_salary_scatter", charts.institution_salary_scatter, lambda: salary_by_institution(days=LOOKBACK_DAYS, min_jobs=2)),
    ("new_vs_repeat_bar", charts.new_vs_repeat_bar, lambda: new_vs_repeat_institutions(weeks=WEEKS)),
    ("longevity_histogram", charts.longevity_histogram, trends.job_longevity_distribution),
    ("market_concentration_line", charts.market_concentration_line, lambda: trends.market_concentration_trends(weeks=WEEKS)),
    ("region_bar", charts.region_bar, lambda: trends.jobs_by_region(days=LOOKBACK_DAYS)),
    ("region_choropleth", charts.region_choropleth, lambda: trends.jobs_by_region(days=LOOKBACK_DAYS)),
    ("top_locations_bar", charts.top_locations_bar, lambda: trends.top_locations(days=LOOKBACK_DAYS, limit=15)),
    ("salary_by_region_bar", charts.salary_by_region_bar, lambda: trends.salary_by_region(days=max(LOOKBACK_DAYS, 90))),
    ("salary_by_contract_bar", charts.salary_by_contract_bar, lambda: trends.salary_by_contract_type(days=max(LOOKBACK_DAYS, 90))),
    ("region_category_heatmap", charts.region_category_heatmap, lambda: trends.region_category_matrix(days=LOOKBACK_DAYS)),
    ("posting_volume_line", charts.posting_volume_line, lambda: trends.daily_postings_trend(days=120)),
    ("weekday_cadence_bar", charts.weekday_cadence_bar, lambda: trends.postings_by_weekday(days=120)),
    ("recruiter_concentration_curve", charts.recruiter_concentration_curve, lambda: institution_posting_distribution(days=max(LOOKBACK_DAYS, 120))),
    ("salary_transparency_breakdown", charts.salary_transparency_breakdown, lambda: trends.salary_disclosure_by_group(days=max(LOOKBACK_DAYS, 120))),
    ("intl_vs_uk_profile_bars", charts.intl_vs_uk_profile_bars, lambda: trends.intl_vs_uk_profile(days=max(LOOKBACK_DAYS, 120))),
    ("casualisation_by_discipline_bar", charts.casualisation_by_discipline_bar, lambda: trends.fixed_term_share_by_discipline(days=180, min_n=40)),
    ("application_window_by_discipline_bar", charts.application_window_by_discipline_bar, lambda: trends.application_window_by_discipline(days=max(LOOKBACK_DAYS, 90), min_n=10)),
    ("precarity_matrix_heatmap", charts.precarity_matrix_heatmap, lambda: trends.contract_hours_matrix(days=max(LOOKBACK_DAYS, 90))),
    ("deadline_pressure_bar", charts.deadline_pressure_bar, trends.deadline_urgency_buckets),
    ("most_reposted_bar", charts.most_reposted_bar, lambda: trends.most_reposted_roles(days=180, limit=15)),
    ("international_destinations_bar", charts.international_destinations_bar, lambda: trends.international_destinations(days=max(LOOKBACK_DAYS, 120), limit=15)),
]


def is_placeholder(fig) -> bool:
    anns = fig.layout.annotations or ()
    return len(fig.data) == 0 and any("data" in (a.text or "").lower() for a in anns)


def main() -> int:
    failures = 0
    for name, builder, fetch in CASES:
        try:
            rows = fetch()
        except Exception as e:
            print(f"FAIL  {name:30s} query error: {e!r}")
            failures += 1
            continue
        n_rows = len(rows) if rows else 0
        try:
            fig = builder(rows)
        except Exception as e:
            print(f"FAIL  {name:30s} chart error ({n_rows} rows): {e!r}")
            failures += 1
            continue
        if is_placeholder(fig):
            status = "EMPTY" if n_rows == 0 else "FAIL "
            if n_rows > 0:
                failures += 1
            print(f"{status} {name:30s} {n_rows} rows -> placeholder figure")
        else:
            print(f"ok    {name:30s} {n_rows} rows -> {len(fig.data)} trace(s)")
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
