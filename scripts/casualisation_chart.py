"""Render the "precarity by discipline" chart as a PNG for sharing (e.g. LinkedIn).

Fixed-term share of advertised posts per subject discipline, sorted, against the
all-adverts baseline, with each discipline coloured by whether it advertises more
research posts (research fellow/associate/assistant, postdoc) than lecturer posts.
The research-to-lecturer ratio is printed beside each label.

Reads the discipline view (`jobs_by_discipline`, so a multi-discipline advert
counts under each of its disciplines) and the jobs table for the baseline.

Requires matplotlib, which is not in requirements.txt (the dashboard uses
Plotly): `pip install matplotlib`.

Usage:
    python -m scripts.casualisation_chart                      # data/jobs.db -> reports/he_casualisation_by_discipline.png
    python -m scripts.casualisation_chart --db path/to/jobs.db --out chart.png
    python -m scripts.casualisation_chart --min-n 150          # stricter per-discipline sample gate
    python -m scripts.casualisation_chart --table              # also print the per-discipline table
"""

import argparse
import re
import sqlite3
from pathlib import Path

from config import DB_PATH, discipline_label

# Title keywords that mark a research post vs a lecturer post (any grade).
_RESEARCH_RE = re.compile(r"research (?:fellow|associate|assistant)|postdoc", re.IGNORECASE)
_LECTURER_RE = re.compile(r"lecturer", re.IGNORECASE)

# Legacy job-type slugs from the pre-June-2026 taxonomy — not disciplines.
_NOT_DISCIPLINES = {"professional-or-managerial", "academic-or-research", "further-education",
                    "craft-or-manual", "clerical", "technical"}

# Palette (validated with the dataviz skill's checker: CVD ΔE 24.7, normal ΔE 33.6, ≥3:1 on surface)
BLUE, ORANGE = "#2a78d6", "#eb6834"          # research-heavy / teaching-heavy
NEUTRAL = "#a3a19a"                           # balanced: de-emphasis grey, deliberately not a third hue
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

# A discipline whose research:lecturer ratio sits inside this band is "balanced" —
# neither research- nor teaching-heavy — so a ratio of 1.0 isn't forced to a side.
BALANCED_BAND = (0.8, 1.25)


def mix_label(res_per_lec: float | None) -> str:
    """'research' | 'teaching' | 'balanced' from the research-posts-per-lecturer-post ratio."""
    if res_per_lec is None:
        return "teaching"          # no lecturer posts at all only happens with no research posts either at our gates
    lo, hi = BALANCED_BAND
    if res_per_lec > hi:
        return "research"
    if res_per_lec < lo:
        return "teaching"
    return "balanced"


_MIX_COLOUR = {"research": BLUE, "teaching": ORANGE, "balanced": NEUTRAL}


def role_flags(title: str) -> tuple[bool, bool]:
    """(is_research_post, is_lecturer_post) from a job title."""
    t = title or ""
    return bool(_RESEARCH_RE.search(t)), bool(_LECTURER_RE.search(t))


def load_data(db_path: Path, min_n: int = 100) -> dict:
    """Per-discipline fixed-term share and research:lecturer ratio, plus baseline metadata.

    Returns {"meta": {...}, "rows": [{category, n, n_contract, fixed, fixed_pct,
    research, lecturer, res_per_lec}, ...]} with rows sorted by fixed_pct ascending
    and only disciplines with at least `min_n` adverts stating a contract type.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        per_disc: dict[str, dict] = {}
        for r in conn.execute(
            "SELECT category, title, contract_type FROM jobs_by_discipline"
        ):
            d = per_disc.setdefault(r["category"], {"n": 0, "n_contract": 0, "fixed": 0,
                                                    "research": 0, "lecturer": 0})
            d["n"] += 1
            if r["contract_type"] in ("permanent", "fixed-term"):
                d["n_contract"] += 1
                d["fixed"] += r["contract_type"] == "fixed-term"
            res, lec = role_flags(r["title"])
            d["research"] += res
            d["lecturer"] += lec

        total, contracted, fixed_all = conn.execute(
            "SELECT COUNT(*), "
            "SUM(contract_type IN ('permanent','fixed-term')), "
            "SUM(contract_type = 'fixed-term') FROM jobs"
        ).fetchone()
        posted_min, posted_max = conn.execute(
            "SELECT MIN(date_posted), MAX(date_posted) FROM jobs WHERE date_posted IS NOT NULL"
        ).fetchone()
    finally:
        conn.close()

    rows = []
    for cat, d in per_disc.items():
        if cat in _NOT_DISCIPLINES or d["n_contract"] < min_n:
            continue
        rows.append({
            "category": cat, **d,
            "fixed_pct": round(100 * d["fixed"] / d["n_contract"], 1),
            "res_per_lec": (round(d["research"] / d["lecturer"], 2) if d["lecturer"] else None),
        })
    rows.sort(key=lambda r: r["fixed_pct"])
    return {
        "meta": {
            "jobs": total, "contracted": contracted or 0,
            "fixed_pct_all": round(100 * (fixed_all or 0) / contracted, 1) if contracted else 0.0,
            "posted_min": posted_min, "posted_max": posted_max, "min_n": min_n,
        },
        "rows": rows,
    }


def render(data: dict, out_path: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import FancyBboxPatch

    rows, meta = data["rows"], data["meta"]
    baseline = meta["fixed_pct_all"]
    plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 13})

    W, H, DPI = 1200, 1500, 100
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=SURFACE)
    ax = fig.add_axes([0.335, 0.11, 0.60, 0.675])
    ax.set_facecolor(SURFACE)

    n = len(rows)
    bar_h = 0.5
    for y, r in enumerate(rows):
        col = _MIX_COLOUR[mix_label(r["res_per_lec"])]
        w = r["fixed_pct"]
        # rounded data end, square at the baseline
        ax.add_patch(FancyBboxPatch((0, y - bar_h / 2), w, bar_h,
                                    boxstyle="round,pad=0,rounding_size=0.25", linewidth=0,
                                    facecolor=col, mutation_aspect=1 / 6.5))
        ax.add_patch(plt.Rectangle((0, y - bar_h / 2), min(1.5, w), bar_h, linewidth=0, facecolor=col))
        ax.text(w + 1.2, y, f"{w:.0f}%", va="center", ha="left", fontsize=12.5, color=INK2)
        ratio = "n/a" if r["res_per_lec"] is None else f"{r['res_per_lec']:.1f}"
        ax.text(-1.5, y, ratio, va="center", ha="right", fontsize=11.5, color=MUTED)

    ax.set_xlim(0, 100)
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_yticks(range(n))
    ax.set_yticklabels([discipline_label(r["category"]) for r in rows], fontsize=13, color=INK)
    ax.tick_params(axis="y", length=0, pad=48)
    ticks = [0, 20, 40, 60, 80, 100]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t}%" for t in ticks], color=MUTED, fontsize=12)
    ax.tick_params(axis="x", length=0, pad=6)
    ax.grid(axis="x", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)

    ax.axvline(baseline, color=INK2, linewidth=1.2, zorder=3)
    ax.text(baseline + 0.8, n - 0.35, f"All adverts: {baseline:.0f}% fixed-term",
            ha="left", va="bottom", fontsize=12, color=INK2)
    ax.text(-1.5, n - 0.35, "Research posts\nper lecturer post", ha="right", va="bottom",
            fontsize=10.5, color=MUTED, linespacing=1.15)

    fig.text(0.04, 0.955, "Precarity in UK higher education is a discipline story",
             fontsize=26, fontweight="semibold", color=INK, ha="left", va="top")
    fig.text(0.04, 0.915, "Share of advertised posts that are fixed-term, by subject discipline",
             fontsize=15, color=INK2, ha="left", va="top")

    handles = [Line2D([0], [0], marker="s", color="none", markerfacecolor=c, markersize=12, linewidth=0)
               for c in (BLUE, NEUTRAL, ORANGE)]
    fig.legend(handles, ["Research-heavy discipline (more research posts than lecturer posts)",
                         "Balanced (about one research post per lecturer post)",
                         "Teaching-heavy discipline (more lecturer posts than research posts)"],
               loc="upper left", bbox_to_anchor=(0.035, 0.885), frameon=False, fontsize=12.5,
               labelcolor=INK2, handletextpad=0.4, borderaxespad=0)

    footer = (
        f"Source: {meta['jobs']:,} adverts on jobs.ac.uk posted {(meta['posted_min'] or '')[:7]} to "
        f"{(meta['posted_max'] or '')[:7]}, scraped daily. Fixed-term share uses the {meta['contracted']:,} "
        "adverts stating a contract type;\n"
        f"disciplines with under {meta['min_n']} such adverts omitted. An advert tagged with several "
        "disciplines counts under each. Role types are classified from the job title.\n"
        "Advertised posts, not the employed workforce."
    )
    fig.text(0.04, 0.04, footer, fontsize=10.5, color=MUTED, ha="left", va="bottom", linespacing=1.5)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI * 2, facecolor=SURFACE)
    plt.close(fig)
    return out_path


def print_table(data: dict) -> None:
    print(f"{'discipline':40s} {'n':>5s} {'fixed%':>7s} {'res/lec':>8s}")
    for r in data["rows"]:
        ratio = "n/a" if r["res_per_lec"] is None else f"{r['res_per_lec']:.2f}"
        print(f"{discipline_label(r['category']):40s} {r['n_contract']:5d} {r['fixed_pct']:7.1f} {ratio:>8s}")
    m = data["meta"]
    print(f"\nAll adverts: {m['fixed_pct_all']}% fixed-term of {m['contracted']:,} stating a contract "
          f"({m['jobs']:,} adverts, posted {m['posted_min']} to {m['posted_max']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the precarity-by-discipline chart")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"SQLite database (default: {DB_PATH})")
    parser.add_argument("--out", type=Path, default=Path("reports/he_casualisation_by_discipline.png"))
    parser.add_argument("--min-n", type=int, default=100,
                        help="Minimum adverts stating a contract type per discipline (default: 100)")
    parser.add_argument("--table", action="store_true", help="Print the per-discipline table too")
    args = parser.parse_args()

    data = load_data(args.db, min_n=args.min_n)
    if args.table:
        print_table(data)
    if not data["rows"]:
        raise SystemExit("No discipline meets the sample gate — nothing to draw.")
    print("wrote", render(data, args.out))


if __name__ == "__main__":
    main()
