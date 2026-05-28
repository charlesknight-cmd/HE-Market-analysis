"""Reusable Plotly figure builders."""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from config import CATEGORY_LABELS

_PALETTE = {
    "academic-or-research":       "#4C72B0",
    "professional-or-managerial": "#DD8452",
    "technical":                  "#55A868",
    "clerical":                   "#C44E52",
    "further-education":          "#8172B3",
    "craft-or-manual":            "#937860",
}

_NO_DATA_MSG = "Not enough data yet — check back as the database fills up"

def _label(slug: str) -> str:
    return CATEGORY_LABELS.get(slug, slug)

def _style_fig(fig: go.Figure) -> go.Figure:
    """Applies modern transparent backgrounds and Outfit typography to charts."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Outfit, -apple-system, sans-serif"),
    )
    fig.update_xaxes(
        gridcolor="rgba(128, 128, 128, 0.12)",
    )
    fig.update_yaxes(
        gridcolor="rgba(128, 128, 128, 0.12)",
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
        line=dict(color="#4C72B0", width=1.5), opacity=0.5,
    ))
    if len(df) >= 3:
        fig.add_trace(go.Scatter(
            x=df["day"], y=df["rolling_7d"],
            mode="lines", name="7-day avg",
            line=dict(color="#DD8452", width=2.5),
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
        marker_color="#4C72B0",
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
    df["colour"] = df["change_pct"].apply(lambda x: "#55A868" if x >= 0 else "#C44E52")
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
        marker_color="#4C72B0",
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
        marker_color="#4C72B0",
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
    colours = {"permanent": "#55A868", "fixed-term": "#DD8452", "flexible": "#8172B3"}
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
    colours = {"full-time": "#4C72B0", "part-time": "#C44E52", "flexible": "#8172B3"}
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
        marker_color="#55A868",
        hovertemplate="Week %{x}<br>First-time: %{y}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=df["week"], y=df["repeat_count"],
        name="Returning recruiters",
        marker_color="#4C72B0",
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
