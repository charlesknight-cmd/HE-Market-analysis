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

from config import discipline_label
from analysis.alerts import check_all, print_alerts
from analysis.institutions import top_institutions, spike_candidates
from analysis.trends import (
    category_growth_wow,
    headline_stats,
    salary_by_discipline,
)


def _divider(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


def run_report(days: int = 30) -> None:
    _divider("HE Job Market — Analysis Report")

    # ── Overview ──────────────────────────────────────────────
    h = headline_stats(days=days)
    prev = f" (previous week {h['prev_week']:,})" if h["prev_week"] is not None else ""
    print(f"\n  Adverts in DB           : {h['total_jobs']:,}")
    print(f"  Last complete week      : {h['last_week']:,} (w/c {h['last_week_label'] or '—'}){prev}")
    print(f"  Posted in last {days} days : {h['n_recent']:,}")
    print(f"  Institutions recruiting : {h['institutions']:,}")
    print(f"  Disciplines             : {h['disciplines']}")

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
            label = discipline_label(r["category"])
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
    _divider("Median Salary Floor by Discipline (full-time, last 180 days)")
    salary = salary_by_discipline(days=180, min_n=20)
    if not salary:
        print("  No salary data available.")
    else:
        print(f"  {'Discipline':<35} {'Median':>10} {'p25':>10} {'p75':>10} {'n':>5}")
        print(f"  {'-'*35} {'-'*10} {'-'*10} {'-'*10} {'-'*5}")
        for r in salary:
            median, p25, p75 = (f"£{r[k]:,.0f}" for k in ("median_salary", "p25", "p75"))
            print(f"  {discipline_label(r['category']):<35} {median:>10} {p25:>10} {p75:>10} {r['n']:>5}")

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
