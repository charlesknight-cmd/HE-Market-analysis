"""Reusable Plotly figure builders."""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from config import CATEGORY_LABELS

# Consistent colour palette per category slug
_PALETTE = {
    "academic-or-research":       "#4C72B0",
    "professional-or-managerial": "#DD8452",
    "technical":                  "#55A868",
    "clerical":                   "#C44E52",
    "further-education":          "#8172B3",
    "craft-or-manual":            "#937860",
}

def _label(slug: str) -> str:
    return CATEGORY_LABELS.get(slug, slug)


def daily_jobs_line(rows: list[dict]) -> go.Figure:
    """Line chart: new jobs per day."""
    if not rows:
        return go.Figure().update_layout(title="No data yet")
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["day"])
    fig = px.line(
        df, x="day", y="job_count",
        labels={"day": "Date", "job_count": "New jobs"},
        title="New job postings per day",
        markers=True,
    )
    fig.update_traces(line_color="#4C72B0", line_width=2)
    fig.update_layout(
        hovermode="x unified",
        xaxis=dict(tickformat="%d %b %Y", dtick="D1"),
    )
    return fig


def category_weekly_bar(rows: list[dict]) -> go.Figure:
    """Stacked bar: weekly postings per category."""
    if not rows:
        return go.Figure().update_layout(title="No data yet")
    df = pd.DataFrame(rows)
    df["category_label"] = df["category"].map(_label)
    fig = px.bar(
        df, x="week", y="job_count", color="category",
        color_discrete_map=_PALETTE,
        labels={"week": "ISO week", "job_count": "Jobs", "category": "Category"},
        title="Weekly postings by category",
        barmode="stack",
    )
    # Override legend labels to friendly names
    for trace in fig.data:
        trace.name = _label(trace.name)
    fig.update_layout(legend_title_text="Category", hovermode="x unified")
    return fig


def category_growth_bar(rows: list[dict]) -> go.Figure:
    """Horizontal bar: week-on-week % change per category."""
    if not rows:
        return go.Figure().update_layout(title="No week-on-week data yet (need 2+ weeks)")
    df = pd.DataFrame([r for r in rows if r["change_pct"] is not None])
    if df.empty:
        return go.Figure().update_layout(title="No week-on-week data yet (need 2+ weeks)")
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
        xaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor="black"),
    )
    return fig


def salary_box_by_category(rows: list[dict]) -> go.Figure:
    """Range bar (min–max) per category for the most recent week."""
    if not rows:
        return go.Figure().update_layout(title="No salary data yet")
    # Keep most recent week per category
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
        xaxis_title="Salary (£)",
        yaxis_title="",
        barmode="overlay",
        showlegend=False,
        xaxis=dict(tickprefix="£", tickformat=","),
    )
    return fig


def top_institutions_bar(rows: list[dict], days: int) -> go.Figure:
    """Horizontal bar: top institutions by posting count."""
    if not rows:
        return go.Figure().update_layout(title="No data yet")
    df = pd.DataFrame(rows).head(15)
    df = df.sort_values("job_count")
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
    return fig


def institution_salary_scatter(rows: list[dict]) -> go.Figure:
    """Scatter: avg salary vs job volume per institution."""
    if not rows:
        return go.Figure().update_layout(title="No salary data yet")
    df = pd.DataFrame(rows)
    fig = px.scatter(
        df, x="avg_salary_min", y="job_count",
        text="institution",
        size="job_count",
        labels={
            "avg_salary_min": "Avg salary floor (£)",
            "job_count": "Jobs posted",
        },
        title="Institutions: salary floor vs posting volume",
    )
    fig.update_traces(textposition="top center")
    fig.update_layout(xaxis=dict(tickprefix="£", tickformat=","))
    return fig
