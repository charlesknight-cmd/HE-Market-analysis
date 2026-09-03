"""Render the "count each advert once and you undercount most subjects" chart as a PNG.

A dumbbell per discipline: adverts counted under their first-listed subject
(one label per advert, the rule a careful analyst would pick) versus counted
under every subject they carry. The ratio between the two is printed beside
each row. Reads the two discipline views, so it reflects whatever the
backfill has captured.

Requires matplotlib (not in requirements.txt): `pip install matplotlib`.

Usage:
    python -m scripts.attribution_chart                       # data/jobs.db -> reports/he_discipline_attribution.png
    python -m scripts.attribution_chart --db path --out chart.png
    python -m scripts.attribution_chart --table               # also print the per-discipline table
"""

import argparse
import sqlite3
from pathlib import Path

from config import DB_PATH, LEGACY_JOB_TYPE_SLUGS, discipline_label

# One hue, two shades (sequential blue steps 250 and 550 from the dataviz palette,
# validated as an ordinal pair), plus chart chrome.
LIGHT, DARK = "#86b6ef", "#1c5cab"
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"


def load_data(db_path: Path) -> dict:
    """Per-discipline advert counts under three attribution rules.

    every_tag     — the advert counts under every academic discipline it carries
    first_listed  — one label per advert: the first subject on its detail page
    first_scanned — one label per advert: the facet the scraper happened to scan
                    first (the project's original, alphabetically biased rule)

    Returns {"meta": {adverts, tags, tags_per_advert, multi_pct, posted_min,
    posted_max, tag_histogram}, "rows": [...]} with rows sorted ascending by
    every_tag / first_listed, legacy job-type slugs dropped.
    """
    conn = sqlite3.connect(db_path)
    try:
        every = dict(conn.execute("SELECT category, COUNT(*) FROM jobs_by_discipline GROUP BY 1").fetchall())
        first_listed = dict(conn.execute("SELECT category, COUNT(*) FROM jobs_primary_discipline GROUP BY 1").fetchall())
        first_scanned = dict(conn.execute("SELECT category, COUNT(*) FROM jobs GROUP BY 1").fetchall())
        adverts = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        tags = conn.execute("SELECT COUNT(*) FROM job_disciplines WHERE facet = 'academic'").fetchone()[0]
        hist = conn.execute(
            "SELECT n, COUNT(*) FROM (SELECT j.job_id, COUNT(d.slug) AS n FROM jobs j "
            "LEFT JOIN job_disciplines d ON d.job_id = j.job_id AND d.facet = 'academic' "
            "GROUP BY j.job_id) GROUP BY n ORDER BY n"
        ).fetchall()
        posted_min, posted_max = conn.execute(
            "SELECT MIN(date_posted), MAX(date_posted) FROM jobs WHERE date_posted IS NOT NULL"
        ).fetchone()
    finally:
        conn.close()

    rows = []
    for cat, n_every in every.items():
        if cat in LEGACY_JOB_TYPE_SLUGS:
            continue
        n_first = first_listed.get(cat, 0)
        rows.append({
            "category": cat, "every_tag": n_every, "first_listed": n_first,
            "first_scanned": first_scanned.get(cat, 0),
            "ratio": round(n_every / n_first, 2) if n_first else None,
        })
    rows.sort(key=lambda r: (r["ratio"] is None, r["ratio"] or 0))
    multi = sum(c for n, c in hist if n >= 2)
    return {
        "meta": {
            "adverts": adverts, "tags": tags,
            "tags_per_advert": round(tags / adverts, 2) if adverts else 0.0,
            "multi_pct": round(100 * multi / adverts, 1) if adverts else 0.0,
            "posted_min": posted_min, "posted_max": posted_max,
            "tag_histogram": [(n, c) for n, c in hist],
        },
        "rows": rows,
    }


def render(data: dict, out_path: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    rows, meta = data["rows"], data["meta"]
    plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 13})

    W, H, DPI = 1200, 1500, 100
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=SURFACE)
    ax = fig.add_axes([0.33, 0.125, 0.56, 0.675])
    ax.set_facecolor(SURFACE)

    n = len(rows)
    xmax = max(r["every_tag"] for r in rows) if rows else 1
    for y, r in enumerate(rows):
        a, b = r["first_listed"], r["every_tag"]
        ax.plot([a, b], [y, y], color=GRID, linewidth=3, solid_capstyle="round", zorder=1)
        ax.plot(a, y, "o", markersize=11, color=LIGHT, markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
        ax.plot(b, y, "o", markersize=11, color=DARK, markeredgecolor=SURFACE, markeredgewidth=2, zorder=4)
        label = "n/a" if r["ratio"] is None else f"×{r['ratio']:.1f}"
        ax.text(b + xmax * 0.02, y, label, va="center", ha="left", fontsize=12.5, color=INK2)

    ax.set_xlim(0, xmax * 1.12)
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_yticks(range(n))
    ax.set_yticklabels([discipline_label(r["category"]) for r in rows], fontsize=13, color=INK)
    ax.tick_params(axis="y", length=0, pad=10)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.tick_params(axis="x", length=0, pad=6, colors=MUTED, labelsize=12)
    ax.set_xlabel("Adverts", color=MUTED, fontsize=12)
    ax.grid(axis="x", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)

    fig.text(0.04, 0.955, "Count each advert once and you undercount most subjects",
             fontsize=25, fontweight="semibold", color=INK, ha="left", va="top")
    fig.text(0.04, 0.915,
             f"Adverts per discipline on jobs.ac.uk: {meta['multi_pct']:.0f}% of adverts carry more than one subject",
             fontsize=15, color=INK2, ha="left", va="top")

    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=c, markersize=11, linewidth=0)
               for c in (LIGHT, DARK)]
    fig.legend(handles, ["Counted once, under the first subject listed on the advert",
                         "Counted under every subject the advert carries"],
               loc="upper left", bbox_to_anchor=(0.035, 0.885), frameon=False, fontsize=12.5,
               labelcolor=INK2, handletextpad=0.4, borderaxespad=0)
    ax.text(0.99, 1.01, "× = how many times larger the full count is", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=11, color=MUTED)

    footer = (
        f"Source: {meta['adverts']:,} adverts on jobs.ac.uk posted {(meta['posted_min'] or '')[:7]} to "
        f"{(meta['posted_max'] or '')[:7]}, scraped daily; subject tags read from each advert's page "
        f"({meta['tags']:,} tags, {meta['tags_per_advert']:.2f} per advert).\n"
        "The site lists an advert's subjects in a fixed taxonomy order, so \"first listed\" favours subjects that "
        "come early in that order. Adverts with no academic subject tag are counted\nunder the facet they were "
        "found in. A few generic calls (fellowship rounds, studentship schemes) carry ten or more tags."
    )
    fig.text(0.04, 0.035, footer, fontsize=10.5, color=MUTED, ha="left", va="bottom", linespacing=1.5)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI * 2, facecolor=SURFACE)
    plt.close(fig)
    return out_path


def print_table(data: dict) -> None:
    print(f"{'discipline':42s} {'every':>6s} {'first-listed':>13s} {'first-scanned':>14s} {'ratio':>6s}")
    for r in data["rows"]:
        ratio = "n/a" if r["ratio"] is None else f"{r['ratio']:.2f}"
        print(f"{discipline_label(r['category']):42s} {r['every_tag']:6d} {r['first_listed']:13d} "
              f"{r['first_scanned']:14d} {ratio:>6s}")
    m = data["meta"]
    print(f"\n{m['adverts']:,} adverts, {m['tags']:,} subject tags ({m['tags_per_advert']} per advert); "
          f"{m['multi_pct']}% carry 2+ subjects. Tags per advert: {m['tag_histogram']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the discipline-attribution dumbbell chart")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"SQLite database (default: {DB_PATH})")
    parser.add_argument("--out", type=Path, default=Path("reports/he_discipline_attribution.png"))
    parser.add_argument("--table", action="store_true", help="Print the per-discipline table too")
    args = parser.parse_args()

    data = load_data(args.db)
    if args.table:
        print_table(data)
    if not data["rows"]:
        raise SystemExit("No disciplines found — nothing to draw.")
    print("wrote", render(data, args.out))


if __name__ == "__main__":
    main()
