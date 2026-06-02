"""Reusable Plotly figure builders."""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from config import CATEGORY_LABELS

_PALETTE = {
    "academic-or-research":       "#4361EE",
    "professional-or-managerial": "#F77F00",
    "technical":                  "#06A77D",
    "clerical":                   "#E5383B",
    "further-education":          "#7209B7",
    "craft-or-manual":            "#8D6E63",
}

# Shared accents used by single-series charts and positive/negative bars.
_ACCENT = "#4361EE"
_POS = "#06A77D"
_NEG = "#E5383B"

_INK = "#1A1A2E"
_GRID = "rgba(26, 26, 46, 0.07)"
_FONT = "Outfit, -apple-system, sans-serif"

_NO_DATA_MSG = "Not enough data yet — check back as the database fills up"

def _label(slug: str) -> str:
    return CATEGORY_LABELS.get(slug, slug)

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
                       "font": {"size": 14, "color": "grey"}}],
    )
    return _style_fig(fig)


# ── Overview charts ───────────────────────────────────────────────────────────

def daily_jobs_line(rows: list[dict]) -> go.Figure:
    """Line chart: new jobs per day with optional 7-day rolling average."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["day"])
    df = df.sort_values("day")
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
            line=dict(color="#F77F00", width=2.5),
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
    """Stacked bar: weekly postings per category."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    fig = px.bar(
        df, x="week", y="job_count", color="category",
        color_discrete_map=_PALETTE,
        labels={"week": "ISO week", "job_count": "Jobs", "category": "Category"},
        title="Weekly postings by category",
        barmode="stack",
    )
    for trace in fig.data:
        trace.name = _label(trace.name)
    fig.update_layout(legend_title_text="Category", hovermode="x unified")
    return _style_fig(fig)


# ── Trends charts ─────────────────────────────────────────────────────────────

def category_share_area(rows: list[dict]) -> go.Figure:
    """Stacked area: category share (%) of total postings per week."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    fig = go.Figure()
    for cat in df["category"].unique():
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
        title="Category share of postings over time (%)",
        xaxis_title="ISO week", yaxis_title="Share (%)",
        yaxis=dict(range=[0, 100]),
        hovermode="x unified",
        legend_title_text="Category",
    )
    return _style_fig(fig)


def seasonal_bar(rows: list[dict]) -> go.Figure:
    """Grouped bar: postings per month per category — reveals seasonal patterns."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    fig = px.bar(
        df, x="month", y="job_count", color="category",
        color_discrete_map=_PALETTE,
        labels={"month": "Month", "job_count": "Jobs", "category": "Category"},
        title="Monthly postings by category",
        barmode="stack",
        text_auto=False,
    )
    for trace in fig.data:
        trace.name = _label(trace.name)
    fig.update_layout(
        legend_title_text="Category",
        hovermode="x unified",
        xaxis=dict(tickangle=-45),
    )
    return _style_fig(fig)


def salary_inflation_line(rows: list[dict]) -> go.Figure:
    """Multi-line chart: average salary floor per category per month."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
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
    fig.update_layout(
        title="Average salary floor by category over time",
        xaxis_title="Month", yaxis_title="Avg salary floor (£)",
        yaxis=dict(tickprefix="£", tickformat=","),
        hovermode="x unified",
        legend_title_text="Category",
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
    """Scatter: avg salary vs job volume per institution."""
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    fig = px.scatter(
        df, x="avg_salary_min", y="job_count",
        text="institution",
        size="job_count",
        labels={"avg_salary_min": "Avg salary floor (£)", "job_count": "Jobs posted"},
        title="Institutions: salary floor vs posting volume",
    )
    fig.update_traces(textposition="top center")
    fig.update_layout(xaxis=dict(tickprefix="£", tickformat=","))
    return _style_fig(fig)


def longevity_histogram(rows: list[dict]) -> go.Figure:
    """Bar chart: distribution of how many days jobs stay visible in the feed."""
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
    fig.update_layout(
        title="How long jobs stay visible in the RSS feed",
        xaxis_title="Days visible",
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
        title="Postings Seasonality Heatmap",
        xaxis_title="Month of Year",
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
        line=dict(color=_ACCENT, width=2.5),
        hovertemplate="Week %{x}<br>Avg Apply Window: %{y:.1f} days<extra></extra>"
    ))
    fig.update_layout(
        title="Average Application Window Length (Days)",
        xaxis_title="ISO Week",
        yaxis_title="Days (Closing - Posted)",
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
        line=dict(color="#7209B7", width=2.5),
        hovertemplate="Week %{x}<br>HHI Concentration: %{y}<br>Volume: %{customdata} jobs<extra></extra>",
        customdata=df["total_jobs"]
    ))
    fig.add_hline(y=1500, line_dash="dash", line_color="green", annotation_text="Competitive (<1500)")
    fig.add_hline(y=2500, line_dash="dash", line_color="orange", annotation_text="Concentrated (>2500)")
    fig.update_layout(
        title="Recruitment Concentration Index (HHI)",
        xaxis_title="ISO Week",
        yaxis_title="HHI Score",
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
        title="Salary Floor Distribution Bands over Time",
        xaxis_title="ISO Week",
        yaxis_title="Salary Floor (£)",
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
        title="Salary Premium by Title Keyword (vs. Category Baseline)",
        xaxis_title="Salary Premium (%)",
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
        line=dict(color=_POS, width=2.5),
        hovertemplate="Week %{x}<br>Permanent Jobs: %{y}%<extra></extra>"
    ))
    fig.update_layout(
        title="Permanent Contract Share Trend (%)",
        xaxis_title="ISO Week",
        yaxis_title="Permanent Contracts (%)",
        yaxis=dict(range=[0, 100]),
        hovermode="x unified",
    )
    return _style_fig(fig)
