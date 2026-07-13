"""Reusable Plotly figure builders."""

import json
import math
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from config import CATEGORY_LABELS, discipline_label

_UK_NATIONS = ["England", "Scotland", "Wales", "Northern Ireland"]
_GEOJSON_PATH = Path(__file__).parent / "assets" / "uk_nations.geojson"
_UK_GEOJSON = None
_UK_GEOJSON_MTIME = None


def _uk_geojson() -> dict:
    """Load and cache the bundled UK-nations boundary GeoJSON.

    The map is drawn with a MapLibre `choroplethmap` trace, which projects the
    polygons on a flat Web-Mercator plane and is therefore indifferent to ring
    winding order — so we serve the file exactly as shipped (no rewinding). This
    is the deliberate cure for the recurring "blank square": Plotly's older geo
    `choropleth` trace renders on a sphere and silently inverts wrong-wound
    rings to fill the whole frame; the MapLibre trace cannot.

    Cache is keyed on the file's mtime so an edit to the geojson is picked up
    on the next call rather than serving a stale copy until the process restarts.
    """
    global _UK_GEOJSON, _UK_GEOJSON_MTIME
    mtime = _GEOJSON_PATH.stat().st_mtime
    if _UK_GEOJSON is None or mtime != _UK_GEOJSON_MTIME:
        with open(_GEOJSON_PATH, encoding="utf-8") as f:
            _UK_GEOJSON = json.load(f)
        _UK_GEOJSON_MTIME = mtime
    return _UK_GEOJSON


def _uk_map_view(gj: dict, width: int = 600, height: int = 520,
                 pad: float = 1.1) -> tuple[dict, float]:
    """Centre + zoom that frame the UK nations for a MapLibre `map` trace.

    Derived from the geojson's bounding box (so it self-adjusts if the boundary
    file is ever swapped) using the standard Web-Mercator fit: choose the zoom
    that makes the bbox fill a reference viewport, binding on whichever axis is
    tighter. The map re-centres responsively to its container but keeps this zoom.
    """
    lons: list[float] = []
    lats: list[float] = []
    for feat in gj.get("features", []):
        geom = feat.get("geometry", {})
        polys = geom.get("coordinates", [])
        if geom.get("type") == "Polygon":
            polys = [polys]
        for poly in polys:
            for ring in poly:
                for lon, lat in ring:
                    lons.append(lon)
                    lats.append(lat)
    if not lons:
        return {"lat": 55.0, "lon": -3.5}, 4.0

    # Clamp the northern extent: the Shetland Isles (~60.9°N) sit far offshore
    # above largely empty ocean, and fitting them shrinks the main landmass to a
    # speck. Cap the fit at 59.5°N so Shetland rests just past the top edge while
    # the mainland fills the frame. (This is a UK-nations map, so a fixed cap is
    # appropriate rather than a general heuristic.)
    min_lon, max_lon = min(lons), max(lons)
    min_lat = min(lats)
    max_lat = min(max(lats), 59.5)
    center = {"lon": (min_lon + max_lon) / 2, "lat": (min_lat + max_lat) / 2}

    def _merc(lat: float) -> float:
        s = min(max(math.sin(math.radians(lat)), -0.9999), 0.9999)
        return math.log((1 + s) / (1 - s)) / 2

    world = 512.0  # MapLibre logical tile size
    lat_frac = (_merc(max_lat) - _merc(min_lat)) / math.pi * pad
    lon_frac = (max_lon - min_lon) / 360 * pad
    lat_zoom = math.log2(height / world / lat_frac) if lat_frac > 0 else 4.0
    lon_zoom = math.log2(width / world / lon_frac) if lon_frac > 0 else 4.0
    zoom = max(0.0, min(lat_zoom, lon_zoom, 18.0))
    return center, zoom

# jobs.ac.uk categorises by subject discipline (21) rather than the old six
# job-types, so the palette must keep up to 8 simultaneously-shown disciplines
# (the multi-category charts fold to top-8-by-volume + grey "Other") mutually
# distinguishable under colour-vision deficiency. Plotly's Light24+Dark24 has many
# pairs that collapse under CVD, so we replace it with a verified CVD-safe set.
#
# Base = the Okabe-Ito 8-colour CVD-safe palette (7 chromatic hues + a dark
# anchor: Okabe's pure black is swapped for #3B2C5E, a near-black blue-violet that
# reads as a "dark" series on white yet harmonises with _ACCENT/_INK; it behaves
# identically to black under CVD simulation). Extended to 12 by a greedy search
# that, at each step, added the hue MAXIMISING the minimum pairwise CIELAB dE of
# the whole set under simulated protanopia, deuteranopia AND tritanopia (Machado
# 2009 matrices, sRGB->linear->simulate->CIELAB). The four extensions
# (#682727 -> #8D0202 -> #EA3E3E -> #DCAF6A) form a maroon->red->bright-red->tan
# family separated mainly by LUMINANCE: past ~8 hues, lightness is the only axis a
# dichromat can still resolve, so the optimiser packs the extras there rather than
# inventing "new" hues that would collapse onto the base.
#
# VERIFIED (Machado 2009, CIEDE76; reproduced independently): worst-case
# (tritanopia) minimum pairwise dE = 16.05 across ALL 12 colours
# (normal 26.43 / protan 18.11 / deutan 16.23 / tritan 16.05), comfortably above
# the ~10-11 "categorically distinct" threshold. CRUCIALLY, because that floor
# holds over the FULL set, ANY subset -- including whichever arbitrary top-8-by-
# volume disciplines a chart folds to -- is guaranteed >= 16.05 under every CVD
# type. That dissolves the old Light24+Dark24 collapsing-pair problem regardless
# of which 8 series surface, which is exactly why stable_per_slug is safe here.
_QUALITATIVE = [
    "#E69F00",  # Okabe-Ito orange
    "#56B4E9",  # Okabe-Ito sky blue
    "#009E73",  # Okabe-Ito bluish green
    "#F0E442",  # Okabe-Ito yellow
    "#0072B2",  # Okabe-Ito blue
    "#D55E00",  # Okabe-Ito vermilion
    "#CC79A7",  # Okabe-Ito reddish purple
    "#3B2C5E",  # dark blue-violet anchor (replaces Okabe-Ito black)
    "#682727",  # dark maroon       -. luminance-stepped red family: the CVD-robust
    "#8D0202",  # deep red          |  way to add categories beyond the 8 hues a
    "#EA3E3E",  # bright red        |  dichromat can resolve -- they separate by
    "#DCAF6A",  # tan / muted gold  -' lightness, not hue.
]

_OTHER = "__other__"  # bucket for the long tail in top-N charts
_LEGACY_SLUGS = [
    "academic-or-research", "professional-or-managerial", "technical",
    "clerical", "further-education", "craft-or-manual",
]

# stable_per_slug assignment: cycle the palette over slugs in a FIXED order (live
# disciplines in CATEGORY_LABELS order, then legacy job-type slugs) so each
# discipline keeps the SAME colour across every chart, aiding cross-chart
# recognition. TRADE-OFF: a given chart shows an arbitrary top-8-by-volume subset
# of the 27 slugs, so the 8 shown are NOT necessarily the palette's first 8 slots
# -- but since the worst-case CVD floor (16.05) holds for the WHOLE palette, every
# possible 8-subset is CVD-safe, so stability costs us nothing in
# distinguishability. (12 colours < 27 slugs, so 3 colours repeat on the long
# tail; those slugs only ever render folded inside grey _OTHER, so the repeats
# never co-occur on screen.)
_PALETTE = {
    slug: _QUALITATIVE[i % len(_QUALITATIVE)]
    for i, slug in enumerate(list(CATEGORY_LABELS.keys()) + _LEGACY_SLUGS)
}
_PALETTE[_OTHER] = "#9AA0A6"  # neutral grey for the folded "Other" bucket

# How many categories to show individually before folding the rest into "Other"
# / before trimming long-tail series on the busier multi-category charts.
_TOP_N = 8

# Shared accents used by single-series charts and positive/negative bars.
_ACCENT = "#4361EE"
_POS = "#06A77D"
_NEG = "#E5383B"
_OTHER_COLOUR = "#9AA0A6"  # muted grey for de-emphasised bars (e.g. weekends)

_INK = "#1A1A2E"
# Secondary text (captions, subtitles, in-plot notes). Darker than a plain
# "grey" (~3.5:1 on white, fails WCAG AA) — this clears 4.5:1 at small sizes.
_MUTED = "#5B6273"
_GRID = "rgba(26, 26, 46, 0.07)"
_FONT = "Outfit, -apple-system, sans-serif"

_NO_DATA_MSG = "Not enough data yet — check back as the database fills up"

def _label(slug: str) -> str:
    if slug == _OTHER:
        return "Other disciplines"
    return discipline_label(slug)


# Public re-export so app chrome (KPIs, tables, filters) shares the figures'
# humanising resolver. Backed by the single source of truth in config.
category_label = discipline_label


def _fold_categories(df: pd.DataFrame, value_col: str, cat_col: str = "category",
                     n: int = _TOP_N) -> pd.DataFrame:
    """Keep the `n` largest categories by total `value_col`; relabel the rest as
    `_OTHER`. Keeps the busy multi-category charts legible now that there are 21
    disciplines instead of six job-types. Caller re-aggregates as needed.
    """
    totals = df.groupby(cat_col)[value_col].sum().sort_values(ascending=False)
    if len(totals) <= n:
        return df
    keep = set(totals.head(n).index)
    out = df.copy()
    out[cat_col] = out[cat_col].where(out[cat_col].isin(keep), _OTHER)
    return out


def _ordered_categories(cats) -> list[str]:
    """Stable category order with the 'Other' bucket always last."""
    cats = list(cats)
    return [c for c in cats if c != _OTHER] + ([_OTHER] if _OTHER in cats else [])

def _style_fig(fig: go.Figure) -> go.Figure:
    """Applies a cohesive light theme, large readable type, and polished hover."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=_FONT, size=14, color=_INK),
        title=dict(
            font=dict(family=_FONT, size=20, color=_INK),
            x=0.01, xanchor="left", y=0.96, yanchor="top",
            pad=dict(b=14),
        ),
        margin=dict(l=64, r=28, t=72, b=56),
        colorway=list(_PALETTE.values()),
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="rgba(26, 26, 46, 0.12)",
            font=dict(family=_FONT, size=13, color=_INK),
        ),
        legend=dict(font=dict(size=12, color=_INK)),
    )
    # Soften every bar with rounded corners; on stacked bars also add a thin white
    # separator so adjacent segments stay distinguishable without relying on hue
    # alone — a colour-vision-deficiency aid that matters most on the many-series
    # stacked discipline charts.
    stacked = getattr(fig.layout, "barmode", None) == "stack"
    for trace in fig.data:
        if trace.type == "bar":
            trace.marker.cornerradius = 5
            if stacked:
                trace.marker.line = dict(width=0.8, color="white")
    fig.update_xaxes(
        gridcolor=_GRID, zerolinecolor=_GRID, linecolor=_GRID,
        title_font=dict(size=13, color=_INK), tickfont=dict(size=12, color=_INK),
    )
    fig.update_yaxes(
        gridcolor=_GRID, zerolinecolor=_GRID, linecolor=_GRID,
        title_font=dict(size=13, color=_INK), tickfont=dict(size=12, color=_INK),
    )
    return fig


def _empty(msg: str = _NO_DATA_MSG) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        xaxis={"visible": False}, yaxis={"visible": False},
        annotations=[{"text": msg, "xref": "paper", "yref": "paper",
                       "x": 0.5, "y": 0.5, "showarrow": False,
                       "font": {"size": 14, "color": _MUTED}}],
    )
    return _style_fig(fig)


# ── Overview charts ───────────────────────────────────────────────────────────

def daily_jobs_line(rows: list[dict]) -> go.Figure:
    """Line chart: new jobs per day with optional 7-day rolling average.

    Days with no new postings (weekends, mostly) produce no row in the query,
    so the series is reindexed onto a contiguous daily range and zero-filled
    BEFORE the rolling mean — otherwise the average skips quiet days entirely
    and reads too high.
    """
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["day"])
    df = df.sort_values("day").set_index("day")
    full = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full, fill_value=0).rename_axis("day").reset_index()
    df["rolling_7d"] = df["job_count"].rolling(7, min_periods=1).mean().round(1)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["day"], y=df["job_count"],
        mode="lines+markers", name="Daily",
        line=dict(color=_ACCENT, width=1.5), opacity=0.5,
    ))
    if len(df) >= 3:
        fig.add_trace(go.Scatter(
            x=df["day"], y=df["rolling_7d"],
            mode="lines", name="7-day avg",
            line=dict(color="#F77F00", width=2.5, shape="spline"),
            fill="tozeroy", fillcolor="rgba(247, 127, 0, 0.10)",
        ))
    fig.update_layout(
        title="New job postings per day",
        xaxis=dict(title="Date", tickformat="%d %b %Y"),
        yaxis=dict(title="New jobs"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return _style_fig(fig)


def category_weekly_bar(rows: list[dict]) -> go.Figure:
    """Stacked bar: weekly postings per discipline (top disciplines + Other)."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    df = _fold_categories(df, "job_count")
    df = df.groupby(["week", "category"], as_index=False)["job_count"].sum()
    fig = px.bar(
        df, x="week", y="job_count", color="category",
        color_discrete_map=_PALETTE,
        category_orders={"category": _ordered_categories(df["category"].unique())},
        labels={"week": "ISO week", "job_count": "Jobs", "category": "Discipline"},
        title="Weekly postings by discipline",
        barmode="stack",
    )
    for trace in fig.data:
        trace.name = _label(trace.name)
    fig.update_layout(legend_title_text="Discipline", hovermode="x unified")
    return _style_fig(fig)


# ── Trends charts ─────────────────────────────────────────────────────────────

def category_share_area(rows: list[dict]) -> go.Figure:
    """Stacked area: discipline share (%) of postings per week (top + Other)."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    df = _fold_categories(df, "share_pct")
    df = df.groupby(["week", "category"], as_index=False)["share_pct"].sum()
    fig = go.Figure()
    for cat in _ordered_categories(df["category"].unique()):
        cat_df = df[df["category"] == cat].sort_values("week")
        fig.add_trace(go.Scatter(
            x=cat_df["week"], y=cat_df["share_pct"],
            name=_label(cat),
            stackgroup="one",
            mode="lines",
            line=dict(color=_PALETTE.get(cat, "#888")),
            hovertemplate=f"{_label(cat)}: %{{y:.1f}}%<extra></extra>",
        ))
    fig.update_layout(
        title="Discipline share of postings over time (%)",
        xaxis_title="ISO week", yaxis_title="Share (%)",
        yaxis=dict(range=[0, 100]),
        hovermode="x unified",
        legend_title_text="Discipline",
    )
    return _style_fig(fig)


def seasonal_bar(rows: list[dict]) -> go.Figure:
    """Stacked bar: postings per month per discipline (top + Other)."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    df = _fold_categories(df, "job_count")
    df = df.groupby(["month", "category"], as_index=False)["job_count"].sum()
    fig = px.bar(
        df, x="month", y="job_count", color="category",
        color_discrete_map=_PALETTE,
        category_orders={"category": _ordered_categories(df["category"].unique())},
        labels={"month": "Month", "job_count": "Jobs", "category": "Discipline"},
        title="Monthly postings by discipline",
        barmode="stack",
        text_auto=False,
    )
    for trace in fig.data:
        trace.name = _label(trace.name)
    fig.update_layout(
        legend_title_text="Discipline",
        hovermode="x unified",
        xaxis=dict(tickangle=-45),
    )
    return _style_fig(fig)


def salary_inflation_line(rows: list[dict]) -> go.Figure:
    """Multi-line chart: average salary floor per discipline per month.

    Averaging the long tail would be misleading, so rather than fold into an
    "Other" line we show only the best-represented disciplines (most months of
    data) — keeping the chart readable with 21 disciplines in play.
    """
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    top = df.groupby("category").size().sort_values(ascending=False).head(_TOP_N).index
    df = df[df["category"].isin(top)]
    trimmed = df["category"].nunique() < pd.DataFrame(rows)["category"].nunique()
    fig = go.Figure()
    for cat in df["category"].unique():
        cat_df = df[df["category"] == cat].sort_values("month")
        fig.add_trace(go.Scatter(
            x=cat_df["month"], y=cat_df["avg_salary_min"],
            name=_label(cat),
            mode="lines+markers",
            line=dict(color=_PALETTE.get(cat, "#888"), width=2),
            hovertemplate=f"{_label(cat)}: £%{{y:,.0f}}<extra></extra>",
        ))
    title = "Average salary floor by discipline over time"
    if trimmed:
        title += f" (top {_TOP_N})"
    fig.update_layout(
        title=title,
        xaxis_title="Month", yaxis_title="Avg salary floor (£)",
        yaxis=dict(tickprefix="£", tickformat=","),
        hovermode="x unified",
        legend_title_text="Discipline",
    )
    return _style_fig(fig)


# ── Roles charts ──────────────────────────────────────────────────────────────

def title_frequency_bar(rows: list[dict]) -> go.Figure:
    """Horizontal bar: most frequent words in job titles."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows).sort_values("count")
    fig = go.Figure(go.Bar(
        x=df["count"], y=df["term"],
        orientation="h",
        marker_color=_ACCENT,
        text=df["count"],
        textposition="outside",
        hovertemplate="%{y}: %{x} occurrences<extra></extra>",
    ))
    fig.update_layout(
        title="Most frequent words in job titles",
        xaxis_title="Occurrences", yaxis_title="",
        margin=dict(l=120),
    )
    return _style_fig(fig)


def category_growth_bar(rows: list[dict]) -> go.Figure:
    """Horizontal bar: week-on-week % change per category."""
    if not rows:
        return _empty("No week-on-week data yet (need 2+ weeks)")
    df = pd.DataFrame([r for r in rows if r["change_pct"] is not None])
    if df.empty:
        return _empty("No week-on-week data yet (need 2+ weeks)")
    df["label"] = df["category"].map(_label)
    df["colour"] = df["change_pct"].apply(lambda x: _POS if x >= 0 else _NEG)
    df = df.sort_values("change_pct")
    fig = go.Figure(go.Bar(
        x=df["change_pct"], y=df["label"],
        orientation="h",
        marker_color=df["colour"],
        text=df["change_pct"].apply(lambda x: f"{x:+.1f}%"),
        textposition="outside",
        hovertemplate="%{y}: %{x:+.1f}%<extra></extra>",
    ))
    fig.update_layout(
        title="Category growth (week-on-week %)",
        xaxis_title="Change (%)", yaxis_title="",
        xaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor="grey"),
    )
    return _style_fig(fig)


def salary_box_by_category(rows: list[dict]) -> go.Figure:
    """Range bar (min–max) per category for the most recent week."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    df = df.sort_values("week").groupby("category").last().reset_index()
    df["label"] = df["category"].map(_label)
    df = df.dropna(subset=["avg_salary_min", "avg_salary_max"])
    df = df.sort_values("avg_salary_min", ascending=False)
    fig = go.Figure()
    for _, row in df.iterrows():
        color = _PALETTE.get(row["category"], "#888888")
        fig.add_trace(go.Bar(
            name=row["label"],
            x=[row["avg_salary_max"] - row["avg_salary_min"]],
            y=[row["label"]],
            base=[row["avg_salary_min"]],
            orientation="h",
            marker_color=color,
            hovertemplate=(
                f"{row['label']}<br>"
                f"Avg min: £{row['avg_salary_min']:,.0f}<br>"
                f"Avg max: £{row['avg_salary_max']:,.0f}<extra></extra>"
            ),
        ))
    fig.update_layout(
        title="Average salary range by category (most recent week)",
        xaxis=dict(title="Salary (£)", tickprefix="£", tickformat=","),
        yaxis_title="",
        barmode="overlay",
        showlegend=False,
    )
    return _style_fig(fig)


# ── Institutions charts ───────────────────────────────────────────────────────

def top_institutions_bar(rows: list[dict], days: int) -> go.Figure:
    """Horizontal bar: top institutions by posting count."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows).head(15).sort_values("job_count")
    fig = go.Figure(go.Bar(
        x=df["job_count"], y=df["institution"],
        orientation="h",
        marker_color=_ACCENT,
        text=df["job_count"],
        textposition="outside",
        hovertemplate="%{y}: %{x} jobs<extra></extra>",
    ))
    fig.update_layout(
        title=f"Top recruiting institutions (last {days} days)",
        xaxis_title="Jobs posted", yaxis_title="",
    )
    return _style_fig(fig)


def institution_salary_scatter(rows: list[dict]) -> go.Figure:
    """Bubble chart: each institution placed by pay floor (x) and hiring volume (y).

    Labelling every institution turned this into overlapping, unreadable text, so
    only a few standouts are labelled directly — the biggest recruiters and the
    best/worst payers — and the rest are identifiable on hover. Labels are placed
    away from whichever edge they sit near so long names aren't clipped.
    """
    if not rows:
        return _empty()
    df = pd.DataFrame(rows).dropna(subset=["avg_salary_min", "job_count"])
    if df.empty:
        return _empty()
    df = df.sort_values("job_count", ascending=False)

    xmin, xmax = df["avg_salary_min"].min(), df["avg_salary_min"].max()
    xspan = (xmax - xmin) or 1
    ymax = df["job_count"].max()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["avg_salary_min"], y=df["job_count"],
        mode="markers",
        marker=dict(size=13, color=_ACCENT, opacity=0.6,
                    line=dict(width=1, color="white")),
        customdata=df[["institution", "avg_salary_max"]].values,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Salary floor: £%{x:,.0f}<br>"
            "Salary ceiling: £%{customdata[1]:,.0f}<br>"
            "Postings: %{y}<extra></extra>"
        ),
        showlegend=False,
    ))

    # Label only the notable few so the surviving labels are worth reading and
    # don't collide: the biggest recruiters plus the highest/lowest payers.
    notable = (set(df.nlargest(3, "job_count")["institution"])
               | set(df.nlargest(2, "avg_salary_min")["institution"])
               | set(df.nsmallest(1, "avg_salary_min")["institution"]))
    lab = df[df["institution"].isin(notable)].copy()

    def _pos(x: float) -> str:
        if x >= xmax - 0.22 * xspan:
            return "middle left"   # near right edge → text to the left
        if x <= xmin + 0.22 * xspan:
            return "middle right"  # near left edge → text to the right
        return "top center"

    fig.add_trace(go.Scatter(
        x=lab["avg_salary_min"], y=lab["job_count"],
        mode="text", text=lab["institution"],
        textposition=[_pos(x) for x in lab["avg_salary_min"]],
        textfont=dict(size=11, color=_INK),
        hoverinfo="skip", showlegend=False,
    ))

    fig.update_layout(
        title="Institutions: pay floor vs hiring volume",
        xaxis=dict(title="Average salary floor", tickprefix="£", tickformat=",",
                   range=[xmin - 0.12 * xspan, xmax + 0.12 * xspan]),
        yaxis=dict(title="Postings in window", rangemode="tozero",
                   range=[0, ymax * 1.2]),
    )
    return _style_fig(fig)


def longevity_histogram(rows: list[dict]) -> go.Figure:
    """Bar chart: distribution of how many days jobs stay visible in the listings."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    df = df[df["days_visible"] >= 0]
    if df.empty:
        return _empty()
    fig = go.Figure(go.Bar(
        x=df["days_visible"], y=df["job_count"],
        marker_color=_ACCENT,
        hovertemplate="Visible %{x} day(s): %{y} jobs<extra></extra>",
    ))
    maxd = int(df["days_visible"].max())
    fig.update_layout(
        title="How long jobs stay visible in the listings",
        # Bars sit on integer day counts; frame them on [-0.5, max+0.5] so the
        # first bar isn't clipped and Plotly doesn't pad in a meaningless "-1"
        # tick. Force 1-day ticks only on a short span; let Plotly thin them out
        # when the visibility range is wide.
        xaxis=dict(title="Days visible", range=[-0.5, maxd + 0.5],
                   **({"dtick": 1} if maxd <= 21 else {})),
        yaxis_title="Number of jobs",
        bargap=0.1,
    )
    return _style_fig(fig)


def contract_type_bar(rows: list[dict]) -> go.Figure:
    """Stacked bar: permanent vs fixed-term contracts per week."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    colours = {"permanent": _POS, "fixed-term": "#F77F00", "flexible": "#7209B7"}
    labels = {"permanent": "Permanent", "fixed-term": "Fixed-term", "flexible": "Flexible"}
    fig = go.Figure()
    for ctype in df["contract_type"].unique():
        sub = df[df["contract_type"] == ctype].sort_values("week")
        fig.add_trace(go.Bar(
            x=sub["week"], y=sub["job_count"],
            name=labels.get(ctype, ctype),
            marker_color=colours.get(ctype, "#888"),
            hovertemplate=f"{labels.get(ctype, ctype)}: %{{y}}<extra></extra>",
        ))
    fig.update_layout(
        title="Permanent vs fixed-term contracts per week",
        xaxis_title="ISO week", yaxis_title="Jobs",
        barmode="stack",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return _style_fig(fig)


def hours_bar(rows: list[dict]) -> go.Figure:
    """Stacked bar: full-time vs part-time vs flexible hours per week."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    colours = {"full-time": _ACCENT, "part-time": _NEG, "flexible": "#7209B7"}
    labels = {"full-time": "Full-time", "part-time": "Part-time", "flexible": "Flexible"}
    fig = go.Figure()
    for htype in df["hours"].unique():
        sub = df[df["hours"] == htype].sort_values("week")
        fig.add_trace(go.Bar(
            x=sub["week"], y=sub["job_count"],
            name=labels.get(htype, htype),
            marker_color=colours.get(htype, "#888"),
            hovertemplate=f"{labels.get(htype, htype)}: %{{y}}<extra></extra>",
        ))
    fig.update_layout(
        title="Full-time vs part-time jobs per week",
        xaxis_title="ISO week", yaxis_title="Jobs",
        barmode="stack",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return _style_fig(fig)


def new_vs_repeat_bar(rows: list[dict]) -> go.Figure:
    """Stacked bar: new vs returning institutions per week."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["week"], y=df["new_count"],
        name="First-time recruiters",
        marker_color=_POS,
        hovertemplate="Week %{x}<br>First-time: %{y}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=df["week"], y=df["repeat_count"],
        name="Returning recruiters",
        marker_color=_ACCENT,
        hovertemplate="Week %{x}<br>Returning: %{y}<extra></extra>",
    ))
    fig.update_layout(
        title="New vs returning institutions per week",
        xaxis_title="ISO week", yaxis_title="Institutions",
        barmode="stack",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return _style_fig(fig)


def seasonal_heatmap(rows: list[dict]) -> go.Figure:
    """Heatmap: job postings per month per category."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    month_map = {
        "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
        "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"
    }
    df["month_label"] = df["month_num"].map(month_map)

    # Pivot to create a 2D matrix
    pivot = df.pivot(index="category", columns="month_label", values="job_count").fillna(0)

    # Reorder columns to standard calendar year
    month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    cols = [c for c in month_order if c in pivot.columns]
    pivot = pivot[cols]

    y_labels = [_label(c) for c in pivot.index]

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns,
        y=y_labels,
        colorscale="Blues",
        hovertemplate="Category: %{y}<br>Month: %{x}<br>Postings: %{z}<extra></extra>"
    ))
    fig.update_layout(
        title="Postings seasonality heatmap",
        xaxis_title="Month of year",
        yaxis_title="",
    )
    return _style_fig(fig)


def recruitment_window_line(rows: list[dict]) -> go.Figure:
    """Line: average days between posting and application closing."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows).sort_values("week")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["week"], y=df["avg_window_days"],
        mode="lines+markers", name="Apply window",
        line=dict(color=_ACCENT, width=2.5, shape="spline"),
        fill="tozeroy", fillcolor="rgba(67, 97, 238, 0.10)",
        hovertemplate="Week %{x}<br>Avg Apply Window: %{y:.1f} days<extra></extra>"
    ))
    fig.update_layout(
        title="Average application window length (days)",
        xaxis_title="ISO week",
        yaxis_title="Days (closing − posted)",
        hovermode="x unified",
    )
    return _style_fig(fig)


def market_concentration_line(rows: list[dict]) -> go.Figure:
    """Line: weekly recruiting HHI score indicating market diversity."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows).sort_values("week")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["week"], y=df["hhi"],
        mode="lines+markers", name="HHI Index",
        line=dict(color="#7209B7", width=2.5, shape="spline"),
        fill="tozeroy", fillcolor="rgba(114, 9, 183, 0.09)",
        hovertemplate="Week %{x}<br>HHI Concentration: %{y}<br>Volume: %{customdata} jobs<extra></extra>",
        customdata=df["total_jobs"]
    ))
    fig.add_hline(y=1500, line_dash="dash", line_color="green", annotation_text="Competitive (<1500)")
    fig.add_hline(y=2500, line_dash="dash", line_color="orange", annotation_text="Concentrated (>2500)")
    fig.update_layout(
        title="Recruitment concentration index (HHI)",
        xaxis_title="ISO week",
        yaxis_title="HHI score",
        hovermode="x unified",
    )
    return _style_fig(fig)


def salary_percentile_bands(rows: list[dict]) -> go.Figure:
    """Line with filled area: 25th–75th percentile salary floor bands."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows).sort_values("week")
    fig = go.Figure()
    
    # 25th percentile boundary (invisible line)
    fig.add_trace(go.Scatter(
        x=df["week"], y=df["p25"],
        mode="lines", line=dict(width=0),
        showlegend=False, hoverinfo="skip"
    ))
    
    # 75th percentile boundary with fill to next trace (25th)
    fig.add_trace(go.Scatter(
        x=df["week"], y=df["p75"],
        mode="lines", fill="tonexty",
        fillcolor="rgba(76, 114, 176, 0.15)",
        line=dict(width=0),
        name="25th-75th Percentile Band",
    ))
    
    # Median (50th percentile)
    fig.add_trace(go.Scatter(
        x=df["week"], y=df["p50"],
        mode="lines+markers", name="Median Salary Floor",
        line=dict(color=_ACCENT, width=2.5),
        hovertemplate="Week %{x}<br>Median Floor: £%{y:,.0f}<extra></extra>"
    ))
    
    fig.update_layout(
        title="Salary floor distribution bands over time",
        xaxis_title="ISO week",
        yaxis_title="Salary floor (£)",
        yaxis=dict(tickprefix="£", tickformat=","),
        hovermode="x unified",
    )
    return _style_fig(fig)


def keyword_premium_bar(rows: list[dict]) -> go.Figure:
    """Horizontal bar: wage premium of words in job titles relative to category average."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows).head(15).sort_values("premium_pct")
    df["colour"] = df["premium_pct"].apply(lambda x: _POS if x >= 0 else _NEG)
    
    fig = go.Figure(go.Bar(
        x=df["premium_pct"], y=df["term"],
        orientation="h",
        marker_color=df["colour"],
        text=df["premium_pct"].apply(lambda x: f"{x:+.1f}%"),
        textposition="outside",
        hovertemplate="Term: %{y}<br>Salary Premium: %{x:+.1f}%<br>Avg Salary: £%{customdata:,.0f}<extra></extra>",
        customdata=df["avg_salary"]
    ))
    fig.update_layout(
        title="Salary premium by title keyword (vs. category baseline)",
        xaxis_title="Salary premium (%)",
        yaxis_title="",
        xaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor="grey"),
    )
    return _style_fig(fig)


def permanent_ratio_line(rows: list[dict]) -> go.Figure:
    """Line: permanent contracts as a percentage share of weekly postings."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    pivoted = df.pivot(index="week", columns="contract_type", values="job_count").fillna(0)
    if "permanent" not in pivoted.columns:
        pivoted["permanent"] = 0
    totals = pivoted.sum(axis=1)
    pivoted["ratio"] = (pivoted["permanent"] / totals * 100).round(1)
    pivoted = pivoted.reset_index()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pivoted["week"], y=pivoted["ratio"],
        mode="lines+markers", name="% Permanent",
        line=dict(color=_POS, width=2.5, shape="spline"),
        fill="tozeroy", fillcolor="rgba(6, 167, 125, 0.10)",
        hovertemplate="Week %{x}<br>Permanent Jobs: %{y}%<extra></extra>"
    ))
    fig.update_layout(
        title="Permanent contract share trend (%)",
        xaxis_title="ISO week",
        yaxis_title="Permanent contracts (%)",
        yaxis=dict(range=[0, 100]),
        hovermode="x unified",
    )
    return _style_fig(fig)


# ── RSS-native charts (added 2026-06) ──────────────────────────────────────────

def salary_transparency_line(rows: list[dict]) -> go.Figure:
    """Line: weekly share of postings that don't disclose a parseable salary."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows).sort_values("week")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["week"], y=df["undisclosed_pct"],
        mode="lines+markers", name="% undisclosed",
        line=dict(color="#F77F00", width=2.5, shape="spline"),
        fill="tozeroy", fillcolor="rgba(247, 127, 0, 0.10)",
        customdata=df[["undisclosed", "total"]].values,
        hovertemplate=("Week %{x}<br>Undisclosed: %{y}% "
                       "(%{customdata[0]} of %{customdata[1]})<extra></extra>"),
    ))
    fig.update_layout(
        title="Salary transparency: share of postings hiding pay",
        xaxis_title="ISO week", yaxis_title="Salary not disclosed (%)",
        yaxis=dict(range=[0, 100]),
        hovermode="x unified",
    )
    return _style_fig(fig)


def salary_distribution_hist(rows: list[dict]) -> go.Figure:
    """Histogram: distribution of advertised salary floors."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    # Drop non-positive floors: a £0 (or negative) "salary" is a parsing artefact,
    # not a real advertised floor, and otherwise plants a spurious bar at the left
    # edge. Legitimately low part-time/pro-rata salaries are kept.
    df = df[df["salary_min"] > 0]
    if df.empty:
        return _empty()
    fig = go.Figure(go.Histogram(
        x=df["salary_min"],
        marker_color=_ACCENT,
        xbins=dict(size=5000),
        hovertemplate="£%{x}<br>%{y} jobs<extra></extra>",
    ))
    fig.update_layout(
        title="Salary floor distribution",
        xaxis=dict(title="Advertised salary floor (£)", tickprefix="£", tickformat=","),
        yaxis_title="Number of jobs",
        bargap=0.05,
    )
    return _style_fig(fig)


_NO_GEO_MSG = "No location data yet — runs after detail-page enrichment"


def region_bar(rows: list[dict]) -> go.Figure:
    """Horizontal bar: postings per UK nation, with International highlighted."""
    if not rows:
        return _empty(_NO_GEO_MSG)
    df = pd.DataFrame(rows).sort_values("job_count")
    df["colour"] = df["region"].apply(lambda r: _NEG if r == "International" else _ACCENT)
    fig = go.Figure(go.Bar(
        x=df["job_count"], y=df["region"],
        orientation="h",
        marker_color=df["colour"],
        text=df["job_count"],
        textposition="outside",
        hovertemplate="%{y}: %{x} jobs<extra></extra>",
    ))
    fig.update_layout(
        title="Jobs by UK nation / International",
        xaxis_title="Jobs posted", yaxis_title="",
        margin=dict(l=120),
    )
    return _style_fig(fig)


def top_locations_bar(rows: list[dict]) -> go.Figure:
    """Horizontal bar: top hiring towns/cities."""
    if not rows:
        return _empty(_NO_GEO_MSG)
    df = pd.DataFrame(rows).sort_values("job_count")
    fig = go.Figure(go.Bar(
        x=df["job_count"], y=df["location"],
        orientation="h",
        marker_color=_ACCENT,
        text=df["job_count"],
        textposition="outside",
        hovertemplate="%{y}: %{x} jobs<extra></extra>",
    ))
    fig.update_layout(
        title="Top hiring locations",
        xaxis_title="Jobs posted", yaxis_title="",
        margin=dict(l=140),
    )
    return _style_fig(fig)


def seniority_breakdown_bar(rows: list[dict]) -> go.Figure:
    """Horizontal bar: posting volume per seniority band, median floor on hover."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows).sort_values("count")
    df["median_label"] = df["median_salary"].apply(
        lambda x: f"£{x:,.0f}" if pd.notnull(x) else "n/a"
    )
    # The "Other / Unclassified" catch-all is a non-answer, not a seniority level,
    # and is often the largest bar — mute it so it stops reading as the headline.
    df["colour"] = df["rank"].apply(
        lambda r: _OTHER_COLOUR if r == "Other / Unclassified" else _ACCENT
    )
    fig = go.Figure(go.Bar(
        x=df["count"], y=df["rank"],
        orientation="h",
        marker_color=df["colour"],
        text=df["count"],
        textposition="outside",
        customdata=df["median_label"],
        hovertemplate="%{y}<br>%{x} postings<br>Median floor: %{customdata}<extra></extra>",
    ))
    fig.update_layout(
        title="Postings by seniority band",
        xaxis_title="Number of postings", yaxis_title="",
        margin=dict(l=190),
    )
    return _style_fig(fig)


def application_window_hist(rows: list[dict]) -> go.Figure:
    """Histogram: how long jobs stay open (closing date − posting date)."""
    if not rows:
        return _empty("No posting/closing dates yet — runs after enrichment")
    df = pd.DataFrame(rows)
    median = df["window_days"].median()
    fig = go.Figure(go.Histogram(
        x=df["window_days"],
        marker_color=_ACCENT,
        xbins=dict(size=7),
        hovertemplate="%{x} days open<br>%{y} jobs<extra></extra>",
    ))
    fig.add_vline(
        x=median, line_dash="dash", line_color=_NEG,
        annotation_text=f"median {median:.0f}d", annotation_position="top",
    )
    fig.update_layout(
        title="Time on market — application window length",
        xaxis_title="Days open (posting → closing)", yaxis_title="Number of jobs",
        bargap=0.05,
    )
    return _style_fig(fig)


def upcoming_deadlines_bar(rows: list[dict]) -> go.Figure:
    """Bar: number of open jobs closing in each upcoming week."""
    if not rows:
        return _empty("No upcoming closing dates")
    df = pd.DataFrame(rows)
    fig = go.Figure(go.Bar(
        x=df["week"], y=df["job_count"],
        marker_color=_ACCENT,
        text=df["job_count"], textposition="outside",
        hovertemplate="Week %{x}<br>%{y} jobs closing<extra></extra>",
    ))
    fig.update_layout(
        title="Upcoming application deadlines (open jobs by closing week)",
        xaxis_title="ISO week", yaxis_title="Jobs closing",
    )
    return _style_fig(fig)


def _median_salary_bar(rows: list[dict], title: str, highlight_intl: bool = False) -> go.Figure:
    """Shared horizontal bar of median salary floor per group."""
    if not rows:
        return _empty("Not enough salaried jobs yet")
    df = pd.DataFrame(rows).sort_values("median_salary")
    if highlight_intl:
        df["colour"] = df["group"].apply(lambda g: _NEG if g == "International" else _ACCENT)
    else:
        df["colour"] = _ACCENT
    fig = go.Figure(go.Bar(
        x=df["median_salary"], y=df["group"],
        orientation="h",
        marker_color=df["colour"],
        text=df["median_salary"].apply(lambda x: f"£{x:,.0f}"),
        textposition="outside",
        customdata=df["n"],
        hovertemplate="%{y}<br>Median floor: £%{x:,.0f}<br>(%{customdata} salaried jobs)<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis=dict(title="Median salary floor (£)", tickprefix="£", tickformat=","),
        yaxis_title="",
        margin=dict(l=140),
    )
    return _style_fig(fig)


def salary_by_region_bar(rows: list[dict]) -> go.Figure:
    """Horizontal bar: median salary floor per region."""
    return _median_salary_bar(rows, "Median salary floor by region", highlight_intl=True)


def salary_by_contract_bar(rows: list[dict]) -> go.Figure:
    """Horizontal bar: median salary floor by contract type."""
    df_title = "Median salary floor: permanent vs fixed-term"
    if rows:
        rows = [{**r, "group": r["group"].replace("-", " ").title()} for r in rows]
    return _median_salary_bar(rows, df_title)


def region_category_heatmap(rows: list[dict]) -> go.Figure:
    """Heatmap: posting counts across discipline (y) × region (x).

    Disciplines run down the y-axis (21 of them) against the handful of regions
    on the x-axis — far more legible than the reverse now there are 21 disciplines.
    """
    if not rows:
        return _empty(_NO_GEO_MSG)
    df = pd.DataFrame(rows)
    df["cat"] = df["category"].map(_label)
    pivot = df.pivot_table(index="cat", columns="region",
                           values="job_count", aggfunc="sum", fill_value=0)
    # Pin the region columns to a stable order (all four UK nations, plus
    # International when present) so a nation with zero postings — e.g. Wales —
    # still draws as an empty column instead of silently vanishing and changing
    # the matrix width run to run. Mirrors the choropleth's reindex.
    region_order = list(_UK_NATIONS) + (
        ["International"] if "International" in pivot.columns else []
    )
    region_order += [c for c in pivot.columns if c not in region_order]
    pivot = pivot.reindex(columns=region_order, fill_value=0)
    # Order disciplines by total volume so the busiest sit at the top.
    pivot = pivot.loc[pivot.sum(axis=1).sort_values().index]
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=list(pivot.columns), y=list(pivot.index),
        colorscale="Blues",
        hovertemplate="%{y} · %{x}<br>%{z} jobs<extra></extra>",
        colorbar_title="Jobs",
    ))
    fig.update_layout(
        title="Where disciplines concentrate (discipline × region)",
        xaxis_title="", yaxis_title="",
        xaxis=dict(tickangle=-30),
    )
    return _style_fig(fig)


def region_choropleth(rows: list[dict]) -> go.Figure:
    """Choropleth map: job postings shaded by UK nation.

    Uses the MapLibre `choroplethmap` trace on a blank ("white-bg") basemap —
    no tiles, no token, fully offline — which renders the polygons on a flat
    projection that is immune to geojson winding order. See `_uk_geojson`.
    """
    if not rows:
        return _empty(_NO_GEO_MSG)
    df = pd.DataFrame(rows)
    df = df[df["region"].isin(_UK_NATIONS)]
    if df.empty:
        return _empty("No UK-nation location data yet")
    # Pad nations with no postings to zero so they still draw on the map
    # instead of leaving a hole in the UK outline.
    df = (df.set_index("region")["job_count"]
            .reindex(_UK_NATIONS, fill_value=0)
            .rename_axis("region").reset_index())
    gj = _uk_geojson()
    center, zoom = _uk_map_view(gj)
    fig = go.Figure(go.Choroplethmap(
        geojson=gj,
        locations=df["region"],
        z=df["job_count"],
        featureidkey="properties.name",
        colorscale="Blues",
        zmin=0,
        # A visible grey outline (not white) so nations with few/zero postings
        # — which fill near-white on the pale end of Blues — still show their
        # shape against the white basemap instead of vanishing.
        marker_line_color="#6E7681", marker_line_width=1.0,
        colorbar_title="Jobs",
        hovertemplate="%{location}<br>%{z} jobs<extra></extra>",
    ))
    fig = _style_fig(fig)
    fig.update_layout(
        title="UK job postings by nation",
        map=dict(style="white-bg", center=center, zoom=zoom),
        margin=dict(l=10, r=10, t=70, b=10),
    )
    return fig


def posting_volume_line(rows: list[dict]) -> go.Figure:
    """Line chart: TRUE daily posting volume (by date_posted) + 7-day average.

    Unlike ``daily_jobs_line`` (which counts by first_seen, i.e. when we first
    saw a listing), this keys off each job's real publication date. Missing days
    are reindexed onto a contiguous daily range and filled with 0 *before* the
    rolling mean, so quiet days correctly drag the average down rather than being
    skipped. The earliest ~14 days are dimmed (survivorship undercount: jobs
    posted then may have closed and left the listings before we scraped them) and
    the final 1-2 days are flagged provisional (still being indexed).
    """
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["day"])
    df = df.sort_values("day").set_index("day")

    # Reindex onto a CONTIGUOUS daily range and fill gaps with 0 BEFORE rolling,
    # so the 7-day average reflects quiet days instead of hopping over them.
    full = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full, fill_value=0).rename_axis("day").reset_index()
    df["rolling_7d"] = df["job_count"].rolling(7, min_periods=1).mean().round(1)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["day"], y=df["job_count"],
        mode="lines+markers", name="Daily",
        line=dict(color=_ACCENT, width=1.5), opacity=0.5,
        hovertemplate="%{x|%d %b %Y}<br>%{y} posted<extra></extra>",
    ))
    if len(df) >= 3:
        fig.add_trace(go.Scatter(
            x=df["day"], y=df["rolling_7d"],
            mode="lines", name="7-day avg",
            line=dict(color="#F77F00", width=2.5, shape="spline"),
            fill="tozeroy", fillcolor="rgba(247, 127, 0, 0.10)",
            hovertemplate="%{x|%d %b %Y}<br>7-day avg %{y}<extra></extra>",
        ))

    # Shade the unreliable edges: the earliest ~14 days undercount (survivorship
    # — short-window jobs posted then may have closed before our first scrape)
    # and the final 1-2 days are provisional (still being indexed).
    start = df["day"].min()
    end = df["day"].max()
    warm_end = min(start + pd.Timedelta(days=14), end)
    prov_start = max(end - pd.Timedelta(days=1), start)
    if warm_end > start:
        fig.add_vrect(
            x0=start, x1=warm_end, line_width=0,
            fillcolor="rgba(26, 26, 46, 0.06)", layer="below",
            annotation_text="undercount", annotation_position="top left",
            annotation_font=dict(size=10, color=_MUTED),
        )
    if end > prov_start:
        fig.add_vrect(
            x0=prov_start, x1=end, line_width=0,
            fillcolor="rgba(229, 56, 59, 0.07)", layer="below",
            annotation_text="provisional", annotation_position="top right",
            annotation_font=dict(size=10, color=_MUTED),
        )

    fig.update_layout(
        title="Job postings per day (by true posting date)",
        xaxis=dict(title="Posting date", tickformat="%d %b %Y"),
        yaxis=dict(title="Jobs posted"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return _style_fig(fig)


# Day-of-week order with Monday first; strftime('%w') is 0=Sun..6=Sat.
_WEEKDAY_ORDER = [1, 2, 3, 4, 5, 6, 0]
_WEEKDAY_LABELS = {
    0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat",
}


def weekday_cadence_bar(rows: list[dict]) -> go.Figure:
    """Bar chart: posting cadence by day of week (Mon..Sun).

    Universities publish on working days, so this exposes the weekly rhythm of
    the market. All seven days always render — weekdays absent from the query
    are padded to zero — and weekend bars (typically ~0) are highlighted in a
    muted grey with a note, since a near-empty weekend is itself the finding.
    """
    if not rows:
        return _empty()
    counts = {r["dow"]: r["job_count"] for r in rows}
    days = [_WEEKDAY_LABELS[d] for d in _WEEKDAY_ORDER]
    values = [counts.get(d, 0) for d in _WEEKDAY_ORDER]
    # Weekend bars (Sat=6, Sun=0) get a muted colour so the working-week shape
    # reads at a glance.
    colours = [_OTHER_COLOUR if d in (0, 6) else _ACCENT for d in _WEEKDAY_ORDER]

    fig = go.Figure(go.Bar(
        x=days, y=values,
        marker_color=colours,
        text=values,
        textposition="outside",
        hovertemplate="%{x}: %{y} postings<extra></extra>",
    ))
    weekend_total = counts.get(0, 0) + counts.get(6, 0)
    if weekend_total == 0:
        fig.add_annotation(
            xref="paper", yref="paper", x=0.99, y=0.97,
            xanchor="right", yanchor="top", showarrow=False,
            text="Effectively no weekend posting",
            font=dict(size=11, color=_MUTED),
        )
    fig.update_layout(
        title="Posting cadence by day of week",
        xaxis_title="Day posted", yaxis_title="Postings",
        bargap=0.25,
    )
    return _style_fig(fig)


def recruiter_concentration_curve(rows: list[dict]) -> go.Figure:
    """Lorenz curve of recruiter concentration: how unequally postings are
    spread across institutions.

    x = cumulative share of institutions (smallest recruiters first), y =
    cumulative share of postings. The 45-degree line is perfect equality (every
    institution posts the same); the deeper the curve sags below it, the more a
    handful of institutions dominate hiring. The Gini coefficient (0 = even,
    1 = one recruiter posts everything) and the top-10 institutions' share are
    summarised in the title and an in-plot annotation. Uses the whole
    distribution, so no minimum-N gate.
    """
    if not rows:
        return _empty()
    counts = sorted(int(r["job_count"]) for r in rows)
    n = len(counts)
    total = sum(counts)
    if n == 0 or total == 0:
        return _empty()

    # Gini via the ranked mean-absolute-difference formula (counts ascending).
    cum_weighted = sum(i * c for i, c in enumerate(counts, start=1))
    gini = (2 * cum_weighted) / (n * total) - (n + 1) / n
    gini = max(0.0, min(gini, 1.0))

    top10_share = sum(sorted(counts, reverse=True)[:10]) / total * 100

    # Lorenz points: prepend (0, 0); each step adds one institution.
    xs = [0.0]
    ys = [0.0]
    running = 0
    for i, c in enumerate(counts, start=1):
        running += c
        xs.append(i / n * 100)
        ys.append(running / total * 100)

    fig = go.Figure()
    # Equality reference line.
    fig.add_trace(go.Scatter(
        x=[0, 100], y=[0, 100],
        mode="lines", name="Perfect equality",
        line=dict(color=_INK, width=1.5, dash="dash"),
        hoverinfo="skip",
    ))
    # Lorenz curve, with the gap to equality shaded.
    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="lines", name="Actual distribution",
        line=dict(color=_ACCENT, width=2.5, shape="spline"),
        fill="tonexty", fillcolor="rgba(67, 97, 238, 0.10)",
        hovertemplate=("Bottom %{x:.0f}% of institutions<br>"
                       "post %{y:.0f}% of jobs<extra></extra>"),
    ))
    fig.add_annotation(
        x=2, y=92, xref="x", yref="y",
        text=(f"Gini {gini:.2f}<br>Top 10 = {top10_share:.0f}% of postings"
              f"<br>{n} recruiters · {total} jobs"),
        showarrow=False, align="left",
        font=dict(size=12, color=_INK),
        bgcolor="rgba(255,255,255,0.7)",
    )
    fig.update_layout(
        title=f"Recruiter concentration (Gini {gini:.2f}, top 10 = {top10_share:.0f}%)",
        xaxis=dict(title="Cumulative share of institutions (%)", range=[0, 100]),
        yaxis=dict(title="Cumulative share of postings (%)", range=[0, 100]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return _style_fig(fig)


# Overall undisclosed-salary baseline (~18% on live) drawn as a reference line on
# both panels; the min group size below which a discipline/region is too thin to
# trust a transparency rate.
_TRANSPARENCY_BASELINE_PCT = 18.0
_TRANSPARENCY_MIN_N = 10
_TRANSPARENCY_TOP_DISCIPLINES = 12


def salary_transparency_breakdown(rows: list[dict]) -> go.Figure:
    """Two-panel horizontal bars: % of postings hiding pay, by discipline and region.

    Left panel ranks the worst-offending disciplines (top ~12 by undisclosed
    rate, slugs humanised via ``_label``); the right panel does the same across
    UK nations / International. A dashed baseline marks the overall undisclosed
    share (~18%) so each group reads as above- or below-average for transparency.

    "Undisclosed" is ``salary_min IS NULL`` — a clean signal that is immune to
    the ~82% salary fill rate (a parsed salary that happens to be missing still
    counts as a real "no pay stated"). Groups thinner than ``_TRANSPARENCY_MIN_N``
    are dropped so a couple of postings can't masquerade as a trend; blank and
    'UK (unspecified)' regions are already excluded upstream. International reads
    as ~100% undisclosed because its non-GBP pay never parses — expected, and
    highlighted in red rather than hidden.
    """
    if not rows:
        return _empty()

    df = pd.DataFrame(rows)
    df = df[df["n"] >= _TRANSPARENCY_MIN_N]
    disc = df[df["dim"] == "discipline"].copy()
    reg = df[df["dim"] == "region"].copy()
    if disc.empty and reg.empty:
        return _empty()

    # Worst offenders first for the top-N cut, then ascending so the longest bar
    # sits at the top of each (horizontal) panel.
    disc = disc.sort_values("undisclosed_pct", ascending=False).head(_TRANSPARENCY_TOP_DISCIPLINES)
    disc["label"] = disc["grp"].map(_label)
    disc = disc.sort_values("undisclosed_pct")

    reg["label"] = reg["grp"]
    reg = reg.sort_values("undisclosed_pct")

    # No subplot_titles: the per-panel "baseline" annotation sits at the top and
    # would collide with them — the dimension is named in each x-axis title instead.
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.18)

    fig.add_trace(go.Bar(
        x=disc["undisclosed_pct"], y=disc["label"], orientation="h",
        marker_color=_ACCENT,
        text=disc["undisclosed_pct"].apply(lambda v: f"{v:.0f}%"),
        textposition="outside",
        customdata=disc[["undisclosed", "n"]].values,
        hovertemplate=("%{y}<br>%{x:.1f}% undisclosed "
                       "(%{customdata[0]} of %{customdata[1]})<extra></extra>"),
        showlegend=False,
    ), row=1, col=1)

    reg_colours = [_NEG if g == "International" else _ACCENT for g in reg["grp"]]
    fig.add_trace(go.Bar(
        x=reg["undisclosed_pct"], y=reg["label"], orientation="h",
        marker_color=reg_colours,
        text=reg["undisclosed_pct"].apply(lambda v: f"{v:.0f}%"),
        textposition="outside",
        customdata=reg[["undisclosed", "n"]].values,
        hovertemplate=("%{y}<br>%{x:.1f}% undisclosed "
                       "(%{customdata[0]} of %{customdata[1]})<extra></extra>"),
        showlegend=False,
    ), row=1, col=2)

    for col in (1, 2):
        fig.add_vline(
            x=_TRANSPARENCY_BASELINE_PCT, line_dash="dash", line_color=_INK, opacity=0.5,
            annotation_text=f"baseline {_TRANSPARENCY_BASELINE_PCT:.0f}%",
            annotation_position="top", row=1, col=col,
        )

    # Headroom so the outside %-labels (and the 100% International bar) aren't clipped.
    fig.update_xaxes(title_text="Undisclosed by discipline (%)", ticksuffix="%",
                     rangemode="tozero", range=[0, 110], row=1, col=1)
    fig.update_xaxes(title_text="Undisclosed by region (%)", ticksuffix="%",
                     rangemode="tozero", range=[0, 110], row=1, col=2)
    fig.update_yaxes(title_text="", row=1, col=1)
    fig.update_yaxes(title_text="", row=1, col=2)
    fig.update_layout(
        title="Salary-transparency gap by discipline and region",
        bargap=0.25,
        margin=dict(l=160),
    )
    return _style_fig(fig)


def intl_vs_uk_profile_bars(rows: list[dict]) -> go.Figure:
    """Grouped horizontal bars: International vs UK structural profile (share %).

    Compares the two sides across share-based metrics only — salary-disclosure
    rate, permanent/fixed-term mix and full/part-time mix — so the headcount gap
    between International and UK postings never dominates. Salary disclosure is
    placed at the top and the two series coloured distinctly to make the
    transparency gap the first thing read; no International median-£ is shown
    (International pay is non-GBP, so only the *disclosure rate* is comparable).
    """
    if not rows:
        return _empty(_NO_GEO_MSG)
    by_side = {r["side"]: r for r in rows}
    if "International" not in by_side or "UK" not in by_side:
        return _empty("Need both International and UK postings to compare")

    # Disclosure first (the headline gap), then contract mix, then hours mix.
    metrics = [
        ("pct_salary_disclosed", "Salary disclosed"),
        ("pct_permanent",        "Permanent"),
        ("pct_fixed_term",       "Fixed-term"),
        ("pct_full_time",        "Full-time"),
        ("pct_part_time",        "Part-time"),
    ]
    # Reverse so the first metric (disclosure) sits at the top of the y-axis.
    y_labels = [lbl for _, lbl in metrics][::-1]

    fig = go.Figure()
    for side, colour in [("UK", _ACCENT), ("International", _NEG)]:
        r = by_side[side]
        vals = [r.get(key) for key, _ in metrics][::-1]
        plotted = [v if v is not None else 0 for v in vals]
        fig.add_trace(go.Bar(
            y=y_labels, x=plotted,
            orientation="h",
            name=f"{side} (n={r['total']})",
            marker_color=colour,
            text=[f"{v:.0f}%" if v is not None else "n/a" for v in vals],
            textposition="outside",
            hovertemplate=f"{side} — %{{y}}: %{{x:.1f}}%<extra></extra>",
        ))

    fig.update_layout(
        title="International vs UK: structural profile (share %)",
        xaxis=dict(title="Share of postings (%)", range=[0, 112], ticksuffix="%"),
        yaxis_title="",
        barmode="group",
        bargap=0.3, bargroupgap=0.1,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=130),
    )
    return _style_fig(fig)


def casualisation_by_discipline_bar(rows: list[dict]) -> go.Figure:
    """Diverging bars: each discipline's fixed-term share vs the market baseline.

    The casualisation "league table". The market baseline is the overall
    fixed-term share across the supplied disciplines (sample-weighted by n), drawn
    as a dashed reference line. Each bar spans from that baseline to the
    discipline's own fixed-term %, so length encodes the gap: disciplines more
    casualised than the market run right in _NEG, less casualised run left in
    _POS. Bars are ordered by fixed-term % (least casualised at the bottom), the
    exact share is labelled on each bar, and n shows on hover.
    """
    if not rows:
        return _empty()
    total_n = sum(r["n"] for r in rows)
    if total_n == 0:
        return _empty()
    # Sample-weighted overall fixed-term share = market baseline.
    baseline = sum(r["fixed_term_pct"] * r["n"] for r in rows) / total_n

    df = pd.DataFrame(rows)
    df["label"] = df["category"].map(_label)
    df["delta"] = df["fixed_term_pct"] - baseline
    df["colour"] = df["delta"].apply(lambda d: _NEG if d >= 0 else _POS)
    df = df.sort_values("fixed_term_pct")

    fig = go.Figure(go.Bar(
        x=df["delta"], y=df["label"],
        base=baseline,
        orientation="h",
        marker_color=df["colour"],
        text=df["fixed_term_pct"].apply(lambda p: f"{p:.0f}%"),
        textposition="outside",
        customdata=df[["fixed_term_pct", "n"]].values,
        hovertemplate=("%{y}<br>Fixed-term: %{customdata[0]:.1f}%<br>"
                       "(%{customdata[1]} contracted roles)<extra></extra>"),
    ))
    fig.add_vline(
        x=baseline, line_dash="dash", line_color="grey",
        annotation_text=f"market baseline {baseline:.0f}%",
        annotation_position="top",
    )
    fig.update_layout(
        title="Casualisation league table: fixed-term share by discipline",
        xaxis=dict(title="Fixed-term contracts (%)", ticksuffix="%", range=[0, 100]),
        yaxis_title="",
        margin=dict(l=200),
        showlegend=False,
    )
    return _style_fig(fig)


def application_window_by_discipline_bar(rows: list[dict]) -> go.Figure:
    """Horizontal dot-and-whisker: median days-to-apply per discipline.

    Each discipline is a dot at its median application window, spanned by an IQR
    whisker (p25–p75); a dashed reference line marks the market-wide median so a
    discipline's pace reads instantly against the field. Disciplines are sorted
    fastest-closing at the bottom so the longest windows sit on top.
    """
    if not rows:
        return _empty("No posting/closing dates yet — runs after enrichment")
    df = pd.DataFrame(rows)
    # Sort so the largest median ends up at the top of a horizontal axis.
    df = df.sort_values("median_days", ascending=True)
    df["label"] = df["category"].map(_label)
    market_median = df["market_median"].iloc[0]

    fig = go.Figure()
    # IQR whiskers (p25-p75) as per-row line segments (go.Scatter has no base).
    for _, row in df.iterrows():
        fig.add_trace(go.Scatter(
            x=[row["p25"], row["p75"]], y=[row["label"], row["label"]],
            mode="lines",
            line=dict(color="rgba(67, 97, 238, 0.35)", width=6),
            hoverinfo="skip", showlegend=False,
        ))
    # Median dots.
    fig.add_trace(go.Scatter(
        x=df["median_days"], y=df["label"],
        mode="markers",
        marker=dict(size=12, color=_ACCENT, line=dict(width=1, color="white")),
        customdata=df[["p25", "p75", "n"]].values,
        hovertemplate=(
            "%{y}<br>Median: %{x:.0f} days"
            "<br>IQR: %{customdata[0]:.0f}–%{customdata[1]:.0f} days"
            "<br>(%{customdata[2]} jobs)<extra></extra>"
        ),
        showlegend=False,
    ))
    fig.add_vline(
        x=market_median, line_dash="dash", line_color=_NEG,
        annotation_text=f"market median {market_median:.0f}d",
        annotation_position="top",
    )
    fig.update_layout(
        title="Days-to-apply benchmark by discipline",
        xaxis=dict(title="Application window (days, closing − posted)", rangemode="tozero"),
        yaxis_title="",
        margin=dict(l=200),
    )
    return _style_fig(fig)


def precarity_matrix_heatmap(rows: list[dict]) -> go.Figure:
    """Annotated heatmap of contract_type (rows) x hours (cols) — the precarity matrix.

    Cells carry both the count and its share of the enriched total. The
    fixed-term + part-time "doubly precarious" cell is outlined and emphasised so
    it reads at a glance. Whole-market grain; subtitle states the enriched n.
    """
    if not rows:
        return _empty("No contract/hours data yet — runs after enrichment")
    df = pd.DataFrame(rows)
    total = int(df["job_count"].sum())
    if total == 0:
        return _empty("No contract/hours data yet — runs after enrichment")

    # Fixed axis order so the matrix is always laid out the same way regardless of
    # which combinations happen to be present in the window.
    row_order = ["permanent", "fixed-term"]
    col_order = ["full-time", "part-time", "flexible"]
    row_labels = {"permanent": "Permanent", "fixed-term": "Fixed-term"}
    col_labels = {"full-time": "Full-time", "part-time": "Part-time", "flexible": "Flexible"}

    pivot = (df.pivot_table(index="contract_type", columns="hours",
                            values="job_count", aggfunc="sum", fill_value=0)
               .reindex(index=row_order, columns=col_order, fill_value=0))

    z = pivot.values
    x = [col_labels[c] for c in pivot.columns]
    y = [row_labels[r] for r in pivot.index]

    fig = go.Figure(go.Heatmap(
        z=z, x=x, y=y,
        colorscale="OrRd", zmin=0,
        hovertemplate="%{y} · %{x}<br>%{z} jobs<extra></extra>",
        colorbar_title="Jobs",
    ))

    # Annotate every cell with count + % of total, choosing readable text colour
    # against the OrRd fill (dark text on the pale cells, white on the hot ones).
    zmax = z.max() or 1
    for ri, r_slug in enumerate(pivot.index):
        for ci, c_slug in enumerate(pivot.columns):
            n = int(pivot.iloc[ri, ci])
            pct = n / total * 100
            text_color = "white" if (n / zmax) > 0.55 else _INK
            fig.add_annotation(
                x=x[ci], y=y[ri],
                text=f"<b>{n}</b><br>{pct:.0f}%",
                showarrow=False,
                font=dict(family=_FONT, size=13, color=text_color),
            )

    # Outline the fixed-term + part-time "doubly precarious" cell.
    if "fixed-term" in pivot.index and "part-time" in pivot.columns:
        hi_r = list(pivot.index).index("fixed-term")
        hi_c = list(pivot.columns).index("part-time")
        fig.add_shape(
            type="rect",
            x0=hi_c - 0.5, x1=hi_c + 0.5,
            y0=hi_r - 0.5, y1=hi_r + 0.5,
            line=dict(color=_NEG, width=3),
            fillcolor="rgba(0,0,0,0)",
            layer="above",
        )

    fig.update_layout(
        title=dict(text=("Precarity matrix: contract type × hours"
                         f"<br><span style='font-size:13px;color:{_MUTED}'>"
                         f"enriched subset, n={total:,}</span>")),
        xaxis=dict(title="", side="top"),
        yaxis=dict(title="", autorange="reversed"),
    )
    return _style_fig(fig)


# Add to dashboard/charts.py (Trends > Timing section, e.g. next to upcoming_deadlines_bar).

# Ordered urgency bands (most urgent first) with a red -> green ramp:
# imminent deadlines are red, comfortable ones green.
_DEADLINE_BUCKETS = ["0-3", "4-7", "8-14", "15-30", "30+"]
_DEADLINE_LABELS = {
    "0-3":   "0-3 days",
    "4-7":   "4-7 days",
    "8-14":  "8-14 days",
    "15-30": "15-30 days",
    "30+":   "30+ days",
}
_DEADLINE_COLOURS = {
    "0-3":   _NEG,        # red — closing within 72h
    "4-7":   "#F77F00",   # orange
    "8-14":  "#F4C430",   # amber
    "15-30": "#5BB85B",   # light green
    "30+":   _POS,        # green — plenty of time
}


def deadline_pressure_bar(rows: list[dict]) -> go.Figure:
    """Vertical bar histogram of open jobs by days-to-deadline urgency band.

    Single series across the five ordered bands (0-3 / 4-7 / 8-14 / 15-30 / 30+)
    with a red -> green ramp so the urgent end reads hot. Mirrors the deadline
    pipeline of upcoming_deadlines_bar but framed as time-pressure rather than
    calendar week.
    """
    if not rows:
        return _empty("No upcoming closing dates")
    df = pd.DataFrame(rows)
    df["bucket"] = pd.Categorical(df["bucket"], categories=_DEADLINE_BUCKETS, ordered=True)
    df = df.sort_values("bucket")
    if df["job_count"].sum() == 0:
        return _empty("No upcoming closing dates")
    df["label"] = df["bucket"].map(_DEADLINE_LABELS)
    df["colour"] = df["bucket"].map(_DEADLINE_COLOURS)
    fig = go.Figure(go.Bar(
        x=df["label"], y=df["job_count"],
        marker_color=df["colour"],
        text=df["job_count"], textposition="outside",
        hovertemplate="Closing in %{x}<br>%{y} open jobs<extra></extra>",
    ))
    fig.update_layout(
        title="Deadline pressure — open jobs by time left to apply",
        xaxis=dict(title="Days until deadline", categoryorder="array",
                   categoryarray=[_DEADLINE_LABELS[b] for b in _DEADLINE_BUCKETS]),
        yaxis_title="Open jobs",
        showlegend=False,
    )
    return _style_fig(fig)
