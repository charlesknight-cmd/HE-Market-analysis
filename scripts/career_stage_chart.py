"""Render the "what an advert tells you depends on career stage" chart as a PNG.

Three small-multiple bar panels sharing one row per academic career stage,
junior to senior: the share of adverts that are fixed-term, that state no pay
figure at all, and that give applicants 14 days or less to apply. Stages come
from the title classifier in analysis.trends; PhD studentships and adverts
outside the UK are excluded, so every rate is over UK jobs.

Requires matplotlib (not in requirements.txt): `pip install matplotlib`.

Usage:
    python -m scripts.career_stage_chart                       # data/jobs.db -> reports/he_career_stage.png
    python -m scripts.career_stage_chart --db path --out chart.png
    python -m scripts.career_stage_chart --table               # also print the per-stage table
"""

import argparse
import sqlite3
from datetime import date
from pathlib import Path

from analysis.trends import _classify_seniority, is_studentship
from config import DB_PATH

# Academic ladder, junior to senior, as (classifier band, display label).
STAGES = [
    ("Research Fellow / Postdoc", "Research posts\nand postdocs"),
    ("Teaching Fellow / Tutor", "Teaching fellows\nand tutors"),
    ("Lecturer / Assistant Prof", "Lecturers"),
    ("Senior Lecturer", "Senior lecturers"),
    ("Associate Prof / Reader", "Associate professors\nand readers"),
    ("Professor", "Professors"),
]
UK_REGIONS = ("England", "Scotland", "Wales", "Northern Ireland", "UK (unspecified)")
SHORT_WINDOW_DAYS = 14

# One hue (sequential blue step 550 from the dataviz palette) plus chart chrome,
# matching scripts/attribution_chart.py.
BAR = "#1c5cab"
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"


def _states_pay(salary_min, salary_raw) -> bool:
    """True if the advert gives any pay figure. Hourly rates count as stated: the
    parser leaves salary_min empty for them (it only keeps annual figures)."""
    return salary_min is not None or "hour" in (salary_raw or "").lower()


def load_data(db_path: Path) -> dict:
    """Per-stage counts and rates over UK, non-studentship adverts.

    Returns {"meta": {adverts, posted_min, posted_max}, "rows": [{stage, label,
    n, fixed_pct, no_pay_pct, short_pct, median_window, n_windows}]} in ladder order.
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT title, contract_type, salary_min, salary_raw, date_posted, closing_date
            FROM jobs
            WHERE date_posted IS NOT NULL
              AND region IN ({", ".join("?" for _ in UK_REGIONS)})
            """,
            UK_REGIONS,
        ).fetchall()
    finally:
        conn.close()

    per = {band: {"n": 0, "contracted": 0, "fixed": 0, "no_pay": 0, "windows": []} for band, _ in STAGES}
    adverts, dates = 0, []
    for title, contract, salary_min, salary_raw, posted, closing in rows:
        if is_studentship(title):
            continue
        adverts += 1
        dates.append(posted)
        d = per.get(_classify_seniority(title))
        if d is None:
            continue
        d["n"] += 1
        if contract in ("permanent", "fixed-term"):
            d["contracted"] += 1
            d["fixed"] += contract == "fixed-term"
        d["no_pay"] += not _states_pay(salary_min, salary_raw)
        if closing:
            days = (date.fromisoformat(closing[:10]) - date.fromisoformat(posted)).days
            if 0 <= days <= 180:
                d["windows"].append(days)

    out = []
    for band, label in STAGES:
        d = per[band]
        w = sorted(d["windows"])
        out.append({
            "stage": band, "label": label, "n": d["n"],
            "fixed_pct": 100 * d["fixed"] / d["contracted"] if d["contracted"] else 0.0,
            "no_pay_pct": 100 * d["no_pay"] / d["n"] if d["n"] else 0.0,
            "short_pct": 100 * sum(x <= SHORT_WINDOW_DAYS for x in w) / len(w) if w else 0.0,
            "median_window": w[len(w) // 2] if w else None,
            "n_windows": len(w),
        })
    return {"meta": {"adverts": adverts, "posted_min": min(dates, default=None),
                     "posted_max": max(dates, default=None)},
            "rows": out}


def render(data: dict, out_path: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    rows, meta = data["rows"], data["meta"]
    plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 13})

    W, H, DPI = 1200, 1000, 100
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=SURFACE)
    panels = [
        ("fixed_pct", "Fixed-term"),
        ("no_pay_pct", "No pay figure given"),
        ("short_pct", f"{SHORT_WINDOW_DAYS} days or less to apply"),
    ]
    left, right, gap = 0.235, 0.975, 0.035
    pw = (right - left - gap * (len(panels) - 1)) / len(panels)
    n, bar_h = len(rows), 0.56
    for i, (key, heading) in enumerate(panels):
        ax = fig.add_axes([left + i * (pw + gap), 0.16, pw, 0.60])
        ax.set_facecolor(SURFACE)
        for y, r in enumerate(rows):
            v = r[key]
            # rounded data end, square at the baseline
            ax.add_patch(FancyBboxPatch((0, y - bar_h / 2), v, bar_h,
                                        boxstyle="round,pad=0,rounding_size=0.2", linewidth=0,
                                        facecolor=BAR, mutation_aspect=1 / 14))
            ax.add_patch(plt.Rectangle((0, y - bar_h / 2), min(2, v), bar_h, linewidth=0, facecolor=BAR))
            ax.text(v + 2.5, y, f"{v:.0f}%", va="center", ha="left", fontsize=13, color=INK2)
        ax.set_xlim(0, 100)
        ax.set_ylim(n - 0.4, -0.6)  # junior at the top
        ax.set_yticks(range(n))
        if i == 0:
            # One-line labels get a blank second line so every label sits at the
            # same height above its "n adverts" note.
            ax.set_yticklabels([r["label"] if "\n" in r["label"] else r["label"] + "\n" for r in rows],
                               fontsize=13, color=INK, linespacing=1.1)
            for y, r in enumerate(rows):
                ax.annotate(f"{r['n']:,} adverts", (0, y), xytext=(-12, -22),
                            textcoords="offset points", ha="right", va="center", fontsize=10.5, color=MUTED,
                            annotation_clip=False)
        else:
            ax.set_yticklabels([])
        ax.tick_params(axis="y", length=0, pad=12)
        ax.set_xticks([0, 50, 100])
        ax.set_xticklabels(["0", "50%", "100%"], color=MUTED, fontsize=11.5)
        ax.tick_params(axis="x", length=0, pad=6)
        ax.grid(axis="x", color=GRID, linewidth=1, zorder=0)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.set_title(heading, loc="left", fontsize=14.5, fontweight="semibold", color=INK, pad=14)

    fig.text(0.04, 0.955, "What a UK academic job advert tells you depends on the career stage",
             fontsize=23, fontweight="semibold", color=INK, ha="left", va="top")
    fig.text(0.04, 0.905, "Share of adverts at each stage. Junior posts state the pay and are mostly temporary, "
             "and about a third close\nwithin two weeks. Senior posts are mostly permanent, often leave the pay out, "
             "and stay open longer.",
             fontsize=14, color=INK2, ha="left", va="top", linespacing=1.4)

    footer = (
        f"Source: {meta['adverts']:,} UK adverts on jobs.ac.uk, scraped daily since May 2026, posted up to "
        f"{meta['posted_max']}; PhD studentships and posts outside the UK excluded.\n"
        "Career stage is classified from the job title. "
        "'No pay figure' means no salary or hourly rate at all (for example 'Competitive' or 'Negotiable').\n"
        "Days to apply = closing date minus posting date. Advertised posts, not the employed workforce. "
        "Professor figures rest on under 100 adverts."
    )
    fig.text(0.04, 0.035, footer, fontsize=10.5, color=MUTED, ha="left", va="bottom", linespacing=1.5)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI * 2, facecolor=SURFACE)
    plt.close(fig)
    return out_path


def print_table(data: dict) -> None:
    print(f"{'stage':28s} {'n':>5s} {'fixed%':>7s} {'nopay%':>7s} {'<=14d%':>7s} {'median d':>9s}")
    for r in data["rows"]:
        print(f"{r['stage']:28s} {r['n']:5d} {r['fixed_pct']:7.1f} {r['no_pay_pct']:7.1f} "
              f"{r['short_pct']:7.1f} {str(r['median_window']):>9s}")
    m = data["meta"]
    print(f"\n{m['adverts']:,} UK non-studentship adverts, posted {m['posted_min']} to {m['posted_max']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the career-stage chart")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"SQLite database (default: {DB_PATH})")
    parser.add_argument("--out", type=Path, default=Path("reports/he_career_stage.png"))
    parser.add_argument("--table", action="store_true", help="Print the per-stage table too")
    args = parser.parse_args()

    data = load_data(args.db)
    if args.table:
        print_table(data)
    print("wrote", render(data, args.out))


if __name__ == "__main__":
    main()
