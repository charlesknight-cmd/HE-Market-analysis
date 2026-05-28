"""Streamlit dashboard for HE job market analysis.

Run with:
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px

from db.schema import init_db

@st.cache_resource
def _ensure_db() -> None:
    """Run once per worker process — not on every Streamlit rerun."""
    init_db()

_ensure_db()

from analysis.alerts import check_all
from analysis.institutions import (
    institution_category_breakdown,
    institution_weekly_trend,
    new_vs_repeat_institutions,
    salary_by_institution,
    spike_candidates,
    top_institutions,
)
from analysis.trends import (
    category_growth_wow,
    category_share_over_time,
    category_weekly_counts,
    contract_type_trend,
    daily_new_jobs,
    hours_trend,
    job_longevity_distribution,
    monthly_postings,
    overall_summary,
    salary_by_month,
    salary_trends_by_category,
    title_word_frequency,
)
from config import CATEGORY_LABELS
from dashboard.charts import (
    category_growth_bar,
    category_share_area,
    category_weekly_bar,
    contract_type_bar,
    daily_jobs_line,
    hours_bar,
    institution_salary_scatter,
    longevity_histogram,
    new_vs_repeat_bar,
    salary_box_by_category,
    salary_inflation_line,
    seasonal_bar,
    title_frequency_bar,
    top_institutions_bar,
)
from db.queries import get_all_jobs, last_scrape_time

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="HE Job Market Analysis", page_icon="📊", layout="wide")

# ── Password gate ─────────────────────────────────────────────────────────────

_required_pwd = st.secrets.get("password", "")
if _required_pwd:
    if not st.session_state.get("authenticated"):
        st.title("HE Job Market Analysis")
        pwd = st.text_input("Password", type="password")
        if pwd == _required_pwd:
            st.session_state.authenticated = True
            st.rerun()
        elif pwd:
            st.error("Incorrect password.")
        st.stop()

st.title("HE Job Market Analysis")
st.caption("Data sourced from jobs.ac.uk · refreshes daily at 07:00")

# Inject premium visual custom CSS styles
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"], .stApp {
        font-family: 'Outfit', sans-serif;
    }
    
    h1, h2, h3 {
        font-family: 'Outfit', sans-serif;
        font-weight: 700 !important;
        letter-spacing: -0.02em;
    }
    
    /* Premium Styled metric cards */
    div[data-testid="stMetric"] {
        background: rgba(128, 128, 128, 0.04);
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 16px;
        padding: 20px 24px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.01);
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    }
    
    div[data-testid="stMetric"]:hover {
        transform: translateY(-4px);
        border-color: rgba(128, 128, 128, 0.3);
        background: rgba(128, 128, 128, 0.08);
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.06);
    }
    
    /* Styled Tab bar */
    button[data-baseweb="tab"] {
        font-weight: 500;
        padding: 12px 24px;
        border-radius: 8px 8px 0 0;
        transition: all 0.2s ease;
    }
    
    /* Active tab styling */
    button[aria-selected="true"] {
        background-color: rgba(76, 114, 176, 0.08) !important;
        color: #4C72B0 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filters")
    lookback_days = st.slider("Lookback window (days)", 7, 180, 30, step=7)
    st.divider()
    _last = last_scrape_time()
    if _last:
        st.caption(f"Last scraped: {_last[:16]} UTC")
    else:
        st.caption("No scrape recorded yet")
    st.caption("Charts cache for 5 minutes")

# ── Cached loaders ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def _summary():             return overall_summary()

@st.cache_data(ttl=300)
def _alerts():              return check_all()

@st.cache_data(ttl=300)
def _daily(d):              return daily_new_jobs(days=d)

@st.cache_data(ttl=300)
def _cat_weekly(w):         return category_weekly_counts(weeks=w)

@st.cache_data(ttl=300)
def _cat_growth():          return category_growth_wow()

@st.cache_data(ttl=300)
def _cat_share(w):          return category_share_over_time(weeks=w)

@st.cache_data(ttl=300)
def _monthly(m):            return monthly_postings(months=m)

@st.cache_data(ttl=300)
def _salary_month(m):       return salary_by_month(months=m)

@st.cache_data(ttl=300)
def _salary_trends(w):      return salary_trends_by_category(weeks=w)

@st.cache_data(ttl=300)
def _title_freq(d):         return title_word_frequency(days=d)

@st.cache_data(ttl=300)
def _longevity():           return job_longevity_distribution()

@st.cache_data(ttl=300)
def _top_inst(d):           return top_institutions(days=d, limit=20)

@st.cache_data(ttl=300)
def _spikes(d):             return spike_candidates(days=min(d, 30), threshold=3)

@st.cache_data(ttl=300)
def _salary_inst(d):        return salary_by_institution(days=d, min_jobs=2)

@st.cache_data(ttl=300)
def _new_vs_repeat(w):      return new_vs_repeat_institutions(weeks=w)

@st.cache_data(ttl=300)
def _contract_trend(w):     return contract_type_trend(weeks=w)

@st.cache_data(ttl=300)
def _hours_trend(w):        return hours_trend(weeks=w)

@st.cache_data(ttl=300)
def _all_jobs():            return get_all_jobs()

weeks = max(1, lookback_days // 7)
months = max(1, lookback_days // 30)

# ── Tabs ──────────────────────────────────────────────────────────────────────

t_overview, t_trends, t_roles, t_institutions, t_data = st.tabs(
    ["Overview", "Trends", "Roles", "Institutions", "Data"]
)

# ═══════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

with t_overview:
    summary = _summary()
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total jobs", f"{summary['total_jobs']:,}")
    k2.metric("New (7 days)", f"{summary['new_7d']:,}")
    k3.metric("New (30 days)", f"{summary['new_30d']:,}")
    k4.metric("Institutions", f"{summary['institutions']:,}")
    k5.metric("Categories", summary["categories"])

    st.divider()

    alerts = _alerts()
    if alerts:
        st.subheader("💡 Key Market Insights")
        meta = {
            "critical": {"label": "Significant Surge", "icon": "🔥"},
            "warning":  {"label": "Elevated Activity", "icon": "📈"},
            "info":     {"label": "Market Trend",      "icon": "💡"}
        }
        for a in alerts:
            m = meta.get(a.severity, {"label": "Insight", "icon": "•"})
            msg = a.message
            for slug, label in CATEGORY_LABELS.items():
                msg = msg.replace(slug, label)
            st.info(f"{m['icon']} **{m['label']}** — {msg}")
    else:
        st.success("✅ No unusual activity or trends detected in this window.")

    st.divider()
    col_l, col_r = st.columns(2)
    with col_l:
        st.plotly_chart(daily_jobs_line(_daily(lookback_days)), use_container_width=True, key="daily_jobs")
    with col_r:
        st.plotly_chart(category_weekly_bar(_cat_weekly(weeks)), use_container_width=True, key="cat_weekly")

# ═══════════════════════════════════════════════════════════════════════════════
# TRENDS
# ═══════════════════════════════════════════════════════════════════════════════

with t_trends:
    st.info("Charts fill in as the database accumulates weeks of history.")

    st.plotly_chart(category_share_area(_cat_share(weeks)), use_container_width=True, key="cat_share")
    st.divider()

    col_l, col_r = st.columns(2)
    with col_l:
        st.plotly_chart(seasonal_bar(_monthly(max(months, 3))), use_container_width=True, key="seasonal")
    with col_r:
        st.plotly_chart(salary_inflation_line(_salary_month(max(months, 3))), use_container_width=True, key="salary_inflation")

    st.divider()

    col_l2, col_r2 = st.columns(2)
    with col_l2:
        st.plotly_chart(contract_type_bar(_contract_trend(weeks)), use_container_width=True, key="contract_type")
    with col_r2:
        st.plotly_chart(hours_bar(_hours_trend(weeks)), use_container_width=True, key="hours")

# ═══════════════════════════════════════════════════════════════════════════════
# ROLES
# ═══════════════════════════════════════════════════════════════════════════════

with t_roles:
    col_l, col_r = st.columns(2)

    with col_l:
        st.plotly_chart(
            title_frequency_bar(_title_freq(lookback_days)),
            use_container_width=True,
            key="title_freq",
        )

    with col_r:
        st.plotly_chart(category_growth_bar(_cat_growth()), use_container_width=True, key="cat_growth")

        growth = _cat_growth()
        if growth:
            df_g = pd.DataFrame(growth)
            df_g["category"] = df_g["category"].map(lambda s: CATEGORY_LABELS.get(s, s))
            df_g = df_g.rename(columns={
                "category": "Category", "last_week": "Last week",
                "this_week": "This week", "change_pct": "Change %",
            })
            st.dataframe(df_g, hide_index=True, use_container_width=True)

    st.divider()

    col_l2, col_r2 = st.columns(2)
    with col_l2:
        st.plotly_chart(salary_box_by_category(_salary_trends(weeks)), use_container_width=True, key="salary_box")
    with col_r2:
        sal = _salary_trends(weeks)
        if sal:
            df_s = pd.DataFrame(sal)
            df_s = df_s.sort_values("week").groupby("category").last().reset_index()
            df_s["category"] = df_s["category"].map(lambda s: CATEGORY_LABELS.get(s, s))
            df_s["avg_salary_min"] = df_s["avg_salary_min"].apply(
                lambda x: f"£{x:,.0f}" if x else "—"
            )
            df_s["avg_salary_max"] = df_s["avg_salary_max"].apply(
                lambda x: f"£{x:,.0f}" if x else "—"
            )
            df_s = df_s.rename(columns={
                "category": "Category", "avg_salary_min": "Avg floor",
                "avg_salary_max": "Avg ceiling", "n": "Jobs with salary",
            })
            st.dataframe(
                df_s[["Category", "Avg floor", "Avg ceiling", "Jobs with salary"]],
                hide_index=True, use_container_width=True,
            )

# ═══════════════════════════════════════════════════════════════════════════════
# INSTITUTIONS
# ═══════════════════════════════════════════════════════════════════════════════

with t_institutions:
    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.plotly_chart(
            top_institutions_bar(_top_inst(lookback_days), lookback_days),
            use_container_width=True,
            key="top_inst",
        )

    with col_r:
        st.subheader("Spike watch (last 7 days, >= 3 jobs)")
        spikes = _spikes(lookback_days)
        if spikes:
            df_sp = pd.DataFrame(spikes)[["institution", "job_count", "category_list"]]
            df_sp["category_list"] = df_sp["category_list"].apply(
                lambda s: ", ".join(CATEGORY_LABELS.get(c.strip(), c.strip()) for c in s.split(","))
            )
            df_sp.columns = ["Institution", "Jobs", "Categories"]
            st.dataframe(df_sp, hide_index=True, use_container_width=True)
        else:
            st.info("No spikes detected in this window.")

    st.divider()

    col_l2, col_r2 = st.columns(2)
    with col_l2:
        st.plotly_chart(
            institution_salary_scatter(_salary_inst(lookback_days)),
            use_container_width=True,
            key="inst_salary",
        )
    with col_r2:
        st.plotly_chart(new_vs_repeat_bar(_new_vs_repeat(weeks)), use_container_width=True, key="new_vs_repeat")

    st.divider()

    col_l3, col_r3 = st.columns(2)
    with col_l3:
        st.plotly_chart(longevity_histogram(_longevity()), use_container_width=True, key="longevity")
        st.caption(
            "Days visible = gap between first and last time a job appeared in "
            "the RSS feed. Zero means seen in one scrape only. This is a proxy "
            "for listing duration, not exact close date."
        )

    with col_r3:
        st.subheader("Institution drill-down")
        all_jobs = _all_jobs()
        institutions = sorted(
            {j["institution"] for j in all_jobs if j["institution"]}, key=str.lower
        )
        selected = st.selectbox("Select an institution", institutions)
        if selected:
            trend = institution_weekly_trend(selected, weeks=weeks)
            if trend:
                df_t = pd.DataFrame(trend)
                fig = px.bar(
                    df_t, x="week", y="job_count",
                    labels={"week": "ISO week", "job_count": "Jobs"},
                    title=f"{selected} — weekly postings",
                )
                st.plotly_chart(fig, use_container_width=True, key="inst_drill")
            breakdown = institution_category_breakdown(days=lookback_days)
            inst_rows = [r for r in breakdown if r["institution"] == selected]
            if inst_rows:
                df_b = pd.DataFrame(inst_rows)[["category", "job_count"]]
                df_b["category"] = df_b["category"].map(lambda s: CATEGORY_LABELS.get(s, s))
                df_b.columns = ["Category", "Jobs"]
                st.dataframe(df_b, hide_index=True, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════════════════

with t_data:
    all_jobs = _all_jobs()
    df_all = pd.DataFrame(all_jobs)

    if df_all.empty:
        st.info("No data in database yet. Run the scraper first.")
    else:
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            cat_filter = st.multiselect(
                "Category", options=list(CATEGORY_LABELS.keys()),
                format_func=lambda s: CATEGORY_LABELS.get(s, s),
            )
        with fc2:
            inst_search = st.text_input("Institution contains")
        with fc3:
            salary_min_filter = st.number_input("Min salary floor (£)", value=0, step=5000)

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
            "title": "Title", "institution": "Institution", "category": "Category",
            "salary_raw": "Salary", "first_seen": "First seen", "url": "URL",
        })
        df_display["Category"] = df_display["Category"].map(lambda s: CATEGORY_LABELS.get(s, s))

        st.dataframe(
            df_display, hide_index=True, use_container_width=True,
            column_config={"URL": st.column_config.LinkColumn("URL", display_text="Open")},
        )

        csv = df_filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download as CSV", data=csv,
            file_name="he_jobs_export.csv", mime="text/csv",
        )
