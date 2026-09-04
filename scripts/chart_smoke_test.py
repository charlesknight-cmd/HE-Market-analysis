"""Build every dashboard chart against the local database and report failures.

Each case pairs a chart builder with the query that feeds it on the dashboard,
so a builder that trips on real (or empty) data is caught before deploy.
Run: python -m scripts.chart_smoke_test
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis import trends
from analysis.institutions import (
    institution_posting_distribution,
    salary_by_institution,
    top_institutions,
)
from dashboard import charts

LOOKBACK_DAYS = 30

CASES = [
    # Overview
    ("posting_volume_line", charts.posting_volume_line, lambda: trends.daily_postings_trend(days=120)),
    ("category_weekly_bar", charts.category_weekly_bar, trends.category_weekly_counts),
    ("weekday_cadence_bar", charts.weekday_cadence_bar, lambda: trends.postings_by_weekday(days=120)),
    # Trends
    ("category_share_area", charts.category_share_area, trends.category_share_over_time),
    ("contract_type_bar", charts.contract_type_bar, trends.contract_type_trend),
    ("hours_bar", charts.hours_bar, trends.hours_trend),
    # Pay
    ("salary_distribution_hist", charts.salary_distribution_hist, lambda: trends.salary_distribution(days=LOOKBACK_DAYS)),
    ("salary_by_contract_bar", charts.salary_by_contract_bar, lambda: trends.salary_by_contract_type(days=max(LOOKBACK_DAYS, 90))),
    ("salary_by_discipline_bar", charts.salary_by_discipline_bar, lambda: trends.salary_by_discipline(days=180)),
    ("seniority_salary_ladder_bar", charts.seniority_salary_ladder_bar, lambda: trends.seniority_salary_ladder(days=365, min_n=15)),
    ("salary_transparency_breakdown", charts.salary_transparency_breakdown, lambda: trends.salary_disclosure_by_group(days=120)),
    ("salary_by_region_bar", charts.salary_by_region_bar, lambda: trends.salary_by_region(days=max(LOOKBACK_DAYS, 90))),
    # Contracts & timing
    ("precarity_mix_bar", charts.precarity_mix_bar, lambda: trends.recruitment_mix_by_discipline(days=180, min_n=40)),
    ("precarity_matrix_heatmap", charts.precarity_matrix_heatmap, lambda: trends.contract_hours_matrix(days=90)),
    ("application_window_hist", charts.application_window_hist, lambda: trends.application_window_distribution(days=LOOKBACK_DAYS)),
    ("application_window_by_discipline_bar", charts.application_window_by_discipline_bar, lambda: trends.application_window_by_discipline(days=90, min_n=10)),
    ("upcoming_deadlines_bar", charts.upcoming_deadlines_bar, lambda: trends.upcoming_deadlines(weeks_ahead=8)),
    ("deadline_pressure_bar", charts.deadline_pressure_bar, trends.deadline_urgency_buckets),
    # Roles
    ("seniority_breakdown_bar", charts.seniority_breakdown_bar, lambda: trends.seniority_breakdown(days=365)),
    ("subdiscipline_bar", lambda rows: charts.tag_breakdown_bar(rows, "Sub-disciplines"),
     lambda: trends.subdiscipline_breakdown("computer-sciences", days=180)),
    ("nonacademic_bar", lambda rows: charts.tag_breakdown_bar(rows, "Professional services"),
     lambda: trends.nonacademic_breakdown(days=180)),
    # Institutions
    ("top_institutions_bar", lambda rows: charts.top_institutions_bar(rows, LOOKBACK_DAYS), lambda: top_institutions(days=LOOKBACK_DAYS, limit=20)),
    ("institution_salary_scatter", charts.institution_salary_scatter, lambda: salary_by_institution(days=LOOKBACK_DAYS, min_jobs=2)),
    ("recruiter_concentration_curve", charts.recruiter_concentration_curve, lambda: institution_posting_distribution(days=120)),
    ("most_reposted_bar", charts.most_reposted_bar, lambda: trends.most_reposted_roles(days=180, limit=15)),
    ("region_bar", charts.region_bar, lambda: trends.jobs_by_region(days=LOOKBACK_DAYS)),
    ("top_locations_bar", charts.top_locations_bar, lambda: trends.top_locations(days=LOOKBACK_DAYS, limit=15)),
    ("region_category_heatmap", charts.region_category_heatmap, lambda: trends.region_category_matrix(days=LOOKBACK_DAYS)),
    ("intl_vs_uk_profile_bars", charts.intl_vs_uk_profile_bars, lambda: trends.intl_vs_uk_profile(days=120)),
    ("international_destinations_bar", charts.international_destinations_bar, lambda: trends.international_destinations(days=120, limit=15)),
    # Data
    ("attribution_dumbbell", charts.attribution_dumbbell, trends.attribution_counts),
]


def main() -> int:
    failures = 0
    for name, builder, loader in CASES:
        try:
            rows = loader()
            fig = builder(rows)
            n = len(rows) if hasattr(rows, "__len__") else "?"
            print(f"ok    {name:36s} {n} rows -> {len(fig.data)} trace(s)")
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failures += 1
            print(f"FAIL  {name:36s} {type(exc).__name__}: {exc}")
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
