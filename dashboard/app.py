"""Streamlit dashboard for HE job market analysis.

Run with:
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# Make the project root importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px

from analysis.alerts import check_all
from analysis.institutions import (
    institution_category_breakdown,
    institution_weekly_trend,
    salary_by_institution,
    spike_candidates,
    top_institutions,
)
from analysis.trends import (
    category_growth_wow,
    category_weekly_counts,
    daily_new_jobs,
    overall_summary,
    salary_trends_by_category,
)
from config import CATEGORY_LABELS
from dashboard.charts import (
    category_growth_bar,
    category_weekly_bar,
    daily_jobs_line,
    institution_salary_scatter,
    salary_box_by_category,
    top_institutions_bar,
)
from db.queries import get_all_jobs

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="HE Job Market",
    page_icon="🎓",
    layout="wide",
)

# ── Password gate (skipped if no password configured in secrets.toml) ─────────
_required_pwd = st.secrets.get("password", "")
if _required_pwd:
    if not st.session_state.get("authenticated"):
        st.title("🎓 HE Job Market Analysis")
        pwd = st.text_input("Password", type="password")
        if pwd == _required_pwd:
            st.session_state.authenticated = True
            st.rerun()
        elif pwd:
            st.error("Incorrect password.")
        st.stop()

st.title("🎓 HE Job Market Analysis")
st.caption("Data sourced from jobs.ac.uk · refreshes daily at 07:00")

# ── Sidebar controls ──────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filters")
    lookback_days = st.slider("Lookback window (days)", 7, 180, 30, step=7)
    st.divider()
    if st.button("🔄 Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

# ── Cached data loaders ───────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def _summary():
    return overall_summary()

@st.cache_data(ttl=300)
def _alerts():
    return check_all()

@st.cache_data(ttl=300)
def _daily(days):
    return daily_new_jobs(days=days)

@st.cache_data(ttl=300)
def _cat_weekly(weeks):
    return category_weekly_counts(weeks=weeks)

@st.cache_data(ttl=300)
def _cat_growth():
    return category_growth_wow()

@st.cache_data(ttl=300)
def _salary_trends(weeks):
    return salary_trends_by_category(weeks=weeks)

@st.cache_data(ttl=300)
def _top_inst(days):
    return top_institutions(days=days, limit=20)

@st.cache_data(ttl=300)
def _spikes(days):
    return spike_candidates(days=min(days, 30), threshold=3)

@st.cache_data(ttl=300)
def _salary_inst(days):
    return salary_by_institution(days=days, min_jobs=2)

@st.cache_data(ttl=300)
def _all_jobs():
    return get_all_jobs()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_overview, tab_categories, tab_institutions, tab_data = st.tabs(
    ["Overview", "Categories", "Institutions", "Data"]
)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

with tab_overview:

    summary = _summary()

    # KPI row
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total jobs", f"{summary['total_jobs']:,}")
    k2.metric("New (7 days)", f"{summary['new_7d']:,}")
    k3.metric("New (30 days)", f"{summary['new_30d']:,}")
    k4.metric("Institutions", f"{summary['institutions']:,}")
    k5.metric("Categories", summary["categories"])

    st.divider()

    # Alerts — friendly category names mapped here so no module-reload issues
    alerts = _alerts()
    if alerts:
        st.subheader(f"⚠️ Alerts ({len(alerts)})")
        severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
        for a in alerts:
            # Ensure category slugs in the message are shown as friendly labels
            msg = a.message
            for slug, label in CATEGORY_LABELS.items():
                msg = msg.replace(slug, label)
            icon = severity_icon.get(a.severity, "•")
            st.warning(f"{icon} **{a.severity.upper()}** — {msg}")
    else:
        st.success("✅ No alerts — nothing unusual detected.")

    st.divider()

    # Charts row
    col_left, col_right = st.columns(2)
    weeks = max(1, lookback_days // 7)

    with col_left:
        st.plotly_chart(
            daily_jobs_line(_daily(lookback_days)),
            width="stretch",
        )

    with col_right:
        st.plotly_chart(
            category_weekly_bar(_cat_weekly(weeks)),
            width="stretch",
        )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CATEGORIES
# ═══════════════════════════════════════════════════════════════════════════════

with tab_categories:

    weeks = max(1, lookback_days // 7)
    col_l, col_r = st.columns(2)

    with col_l:
        st.plotly_chart(category_growth_bar(_cat_growth()), width="stretch")

        growth = _cat_growth()
        if growth:
            df_g = pd.DataFrame(growth)
            df_g["category"] = df_g["category"].map(lambda s: CATEGORY_LABELS.get(s, s))
            df_g = df_g.rename(columns={
                "category":   "Category",
                "last_week":  "Last week",
                "this_week":  "This week",
                "change_pct": "Change %",
            })
            st.dataframe(df_g, hide_index=True, width="stretch")

    with col_r:
        st.plotly_chart(salary_box_by_category(_salary_trends(weeks)), width="stretch")

        sal = _salary_trends(weeks)
        if sal:
            df_s = pd.DataFrame(sal)
            df_s = df_s.sort_values(["category", "week"])
            df_s = df_s.groupby("category").last().reset_index()
            df_s["category"] = df_s["category"].map(lambda s: CATEGORY_LABELS.get(s, s))
            df_s["avg_salary_min"] = df_s["avg_salary_min"].apply(
                lambda x: f"£{x:,.0f}" if x else "—"
            )
            df_s["avg_salary_max"] = df_s["avg_salary_max"].apply(
                lambda x: f"£{x:,.0f}" if x else "—"
            )
            df_s = df_s.rename(columns={
                "category":       "Category",
                "avg_salary_min": "Avg floor",
                "avg_salary_max": "Avg ceiling",
                "n":              "Jobs with salary",
            })
            st.dataframe(
                df_s[["Category", "Avg floor", "Avg ceiling", "Jobs with salary"]],
                hide_index=True,
                width="stretch",
            )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — INSTITUTIONS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_institutions:

    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.plotly_chart(
            top_institutions_bar(_top_inst(lookback_days), lookback_days),
            width="stretch",
        )

    with col_r:
        st.subheader("Spike watch (last 7 days, >= 3 jobs)")
        spikes = _spikes(lookback_days)
        if spikes:
            df_sp = pd.DataFrame(spikes)[["institution", "job_count", "category_list"]]
            # Make category slugs readable
            df_sp["category_list"] = df_sp["category_list"].apply(
                lambda s: ", ".join(CATEGORY_LABELS.get(c.strip(), c.strip()) for c in s.split(","))
            )
            df_sp.columns = ["Institution", "Jobs", "Categories"]
            st.dataframe(df_sp, hide_index=True, width="stretch")
        else:
            st.info("No spikes detected in this window.")

    st.divider()

    st.plotly_chart(
        institution_salary_scatter(_salary_inst(lookback_days)),
        width="stretch",
    )

    st.divider()

    # Institution drill-down
    st.subheader("Institution drill-down")
    all_jobs = _all_jobs()
    institutions = sorted(
        {j["institution"] for j in all_jobs if j["institution"]},
        key=str.lower,
    )
    selected = st.selectbox("Select an institution", institutions)
    if selected:
        trend = institution_weekly_trend(selected, weeks=max(1, lookback_days // 7))
        if trend:
            df_t = pd.DataFrame(trend)
            fig = px.bar(
                df_t, x="week", y="job_count",
                labels={"week": "ISO week", "job_count": "Jobs"},
                title=f"{selected} — weekly postings",
            )
            st.plotly_chart(fig, width="stretch")

        breakdown = institution_category_breakdown(days=lookback_days)
        inst_rows = [r for r in breakdown if r["institution"] == selected]
        if inst_rows:
            df_b = pd.DataFrame(inst_rows)[["category", "job_count"]]
            df_b["category"] = df_b["category"].map(lambda s: CATEGORY_LABELS.get(s, s))
            df_b.columns = ["Category", "Jobs"]
            st.dataframe(df_b, hide_index=True, width="stretch")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — DATA
# ═══════════════════════════════════════════════════════════════════════════════

with tab_data:

    all_jobs = _all_jobs()
    df_all = pd.DataFrame(all_jobs)

    if df_all.empty:
        st.info("No data in database yet. Run the scraper first.")
    else:
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            cat_filter = st.multiselect(
                "Category",
                options=list(CATEGORY_LABELS.keys()),
                format_func=lambda s: CATEGORY_LABELS.get(s, s),
            )
        with fc2:
            inst_search = st.text_input("Institution contains")
        with fc3:
            salary_min_filter = st.number_input(
                "Min salary floor (£)", value=0, step=5000
            )

        mask = pd.Series([True] * len(df_all))
        if cat_filter:
            mask &= df_all["category"].isin(cat_filter)
        if inst_search:
            mask &= df_all["institution"].str.contains(inst_search, case=False, na=False)
        if salary_min_filter > 0:
            mask &= df_all["salary_min"] >= salary_min_filter

        df_filtered = df_all[mask].copy()
        st.caption(f"Showing {len(df_filtered):,} of {len(df_all):,} jobs")

        show_cols = ["title", "institution", "category", "salary_raw", "first_seen", "url"]
        df_display = df_filtered[show_cols].rename(columns={
            "title":       "Title",
            "institution": "Institution",
            "category":    "Category",
            "salary_raw":  "Salary",
            "first_seen":  "First seen",
            "url":         "URL",
        })
        df_display["Category"] = df_display["Category"].map(
            lambda s: CATEGORY_LABELS.get(s, s)
        )

        st.dataframe(
            df_display,
            hide_index=True,
            width="stretch",
            column_config={
                "URL": st.column_config.LinkColumn("URL", display_text="Open"),
            },
        )

        csv = df_filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download as CSV",
            data=csv,
            file_name="he_jobs_export.csv",
            mime="text/csv",
        )
