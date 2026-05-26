"""Print a human-readable analysis report to stdout.

Usage:
    python -m analysis.report
    python -m analysis.report --days 14
"""

import argparse
import sys

# Ensure £ and other chars render correctly on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import CATEGORY_LABELS
from analysis.alerts import check_all, print_alerts
from analysis.institutions import top_institutions, spike_candidates
from analysis.trends import (
    category_growth_wow,
    category_weekly_counts,
    overall_summary,
    salary_trends_by_category,
)


def _divider(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


def run_report(days: int = 30) -> None:
    _divider("HE Job Market — Analysis Report")

    # ── Overview ──────────────────────────────────────────────
    summary = overall_summary()
    print(f"\n  Total jobs in DB : {summary['total_jobs']:,}")
    print(f"  New (last 7 days): {summary['new_7d']:,}")
    print(f"  New (last 30 days): {summary['new_30d']:,}")
    print(f"  Institutions seen: {summary['institutions']:,}")
    print(f"  Categories       : {summary['categories']}")

    # ── Alerts ────────────────────────────────────────────────
    _divider("Alerts")
    alerts = check_all()
    print_alerts(alerts)

    # ── Category week-on-week growth ──────────────────────────
    _divider("Category Growth (week-on-week)")
    growth = category_growth_wow()
    if not growth:
        print("  Not enough data yet (need at least 2 weeks of history).")
    else:
        print(f"  {'Category':<35} {'Last wk':>8} {'This wk':>8} {'Change':>8}")
        print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8}")
        for r in growth:
            label = CATEGORY_LABELS.get(r["category"], r["category"])
            pct = f"{r['change_pct']:+.1f}%" if r["change_pct"] is not None else "  n/a"
            print(f"  {label:<35} {r['last_week']:>8} {r['this_week']:>8} {pct:>8}")

    # ── Top recruiters ────────────────────────────────────────
    _divider(f"Top Recruiters (last {days} days)")
    top = top_institutions(days=days, limit=15)
    if not top:
        print("  No data.")
    else:
        print(f"  {'Institution':<45} {'Jobs':>5} {'Cats':>5} {'Avg £min':>10}")
        print(f"  {'-'*45} {'-'*5} {'-'*5} {'-'*10}")
        for r in top:
            avg = f"£{r['avg_salary_min']:,.0f}" if r["avg_salary_min"] else "  —"
            print(
                f"  {r['institution']:<45} {r['job_count']:>5} "
                f"{r['categories']:>5} {avg:>10}"
            )

    # ── Institution spikes ────────────────────────────────────
    _divider("Institution Spikes (last 7 days, >= 3 jobs)")
    spikes = spike_candidates(days=7, threshold=3)
    if not spikes:
        print("  None detected.")
    else:
        for r in spikes:
            print(f"  {r['institution']}: {r['job_count']} jobs ({r['category_list']})")

    # ── Salary snapshot ───────────────────────────────────────
    _divider("Salary Snapshot by Category (most recent week with data)")
    salary = salary_trends_by_category(weeks=4)
    if not salary:
        print("  No salary data available.")
    else:
        # Show only the most recent week per category
        latest: dict[str, dict] = {}
        for r in salary:
            latest[r["category"]] = r
        print(f"  {'Category':<35} {'Avg £min':>10} {'Avg £max':>10} {'n':>5}")
        print(f"  {'-'*35} {'-'*10} {'-'*10} {'-'*5}")
        for cat, r in sorted(latest.items()):
            label = CATEGORY_LABELS.get(cat, cat)
            lo = f"£{r['avg_salary_min']:,.0f}" if r["avg_salary_min"] else "  —"
            hi = f"£{r['avg_salary_max']:,.0f}" if r["avg_salary_max"] else "  —"
            print(f"  {label:<35} {lo:>10} {hi:>10} {r['n']:>5}")

    print(f"\n{'─' * 60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="HE job market analysis report")
    parser.add_argument(
        "--days", type=int, default=30, help="Lookback window in days (default: 30)"
    )
    args = parser.parse_args()
    run_report(days=args.days)


if __name__ == "__main__":
    main()
