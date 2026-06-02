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
    recruitment_window_trends,
    market_concentration_trends,
    salary_percentile_trends,
    keyword_salary_premiums,
    seasonal_heatmap_data,
    salary_transparency_trend,
    salary_distribution,
    seniority_breakdown,
    jobs_by_region,
    top_locations,
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
    seasonal_heatmap,
    recruitment_window_line,
    market_concentration_line,
    salary_percentile_bands,
    keyword_premium_bar,
    permanent_ratio_line,
    salary_transparency_line,
    salary_distribution_hist,
    seniority_breakdown_bar,
    region_bar,
    top_locations_bar,
)
from db.queries import get_all_jobs, last_scrape_time

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="HE Job Market Analysis",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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

_head_left, _head_right = st.columns([5, 1])
with _head_left:
    st.title("HE Job Market Analysis")
    _last = last_scrape_time()
    _scraped = f" · last scraped {_last[:16]} UTC" if _last else ""
    st.caption(f"Data sourced from jobs.ac.uk · refreshes daily at 07:00{_scraped}")
with _head_right:
    with st.popover("⚙ Filters", width="stretch"):
        lookback_days = st.slider("Lookback window (days)", 7, 180, 30, step=7)
        st.caption("Charts cache for 5 minutes")

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
def _all_jobs():            return get_all_jobs()

@st.cache_data(ttl=300)
def _seasonal_heatmap():    return seasonal_heatmap_data()

@st.cache_data(ttl=300)
def _market_concentration(w): return market_concentration_trends(weeks=w)

@st.cache_data(ttl=300)
def _salary_percentiles(w): return salary_percentile_trends(weeks=w)

@st.cache_data(ttl=300)
def _keyword_premiums(d):   return keyword_salary_premiums(days=d)

@st.cache_data(ttl=300)
def _salary_transparency(w): return salary_transparency_trend(weeks=w)

@st.cache_data(ttl=300)
def _salary_dist(d):        return salary_distribution(days=d)

@st.cache_data(ttl=300)
def _seniority(d):          return seniority_breakdown(days=d)

@st.cache_data(ttl=300)
def _contract_trend(w):     return contract_type_trend(weeks=w)

@st.cache_data(ttl=300)
def _hours_trend(w):        return hours_trend(weeks=w)

@st.cache_data(ttl=300)
def _recruitment_window(w): return recruitment_window_trends(weeks=w)

@st.cache_data(ttl=300)
def _region(d):             return jobs_by_region(days=d)

@st.cache_data(ttl=300)
def _top_locations(d):      return top_locations(days=d, limit=15)

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
    col_l, col_r = st.columns(2)
    with col_l:
        st.plotly_chart(daily_jobs_line(_daily(lookback_days)), width='stretch', key="daily_jobs")
    with col_r:
        st.plotly_chart(category_weekly_bar(_cat_weekly(weeks)), width='stretch', key="cat_weekly")

    st.divider()

    alerts = _alerts()
    if alerts:
        st.subheader("💡 Key Market Insights")
        meta = {
            "critical": {"label": "Significant Surge", "icon": "🔥"},
            "warning":  {"label": "Elevated Activity", "icon": "📈"},
            "info":     {"label": "Market Trend",      "icon": "💡"}
        }

        def _render_insight(a):
            m = meta.get(a.severity, {"label": "Insight", "icon": "•"})
            msg = a.message
            for slug, label in CATEGORY_LABELS.items():
                msg = msg.replace(slug, label)
            st.info(f"{m['icon']} **{m['label']}** — {msg}")

        for a in alerts[:3]:
            _render_insight(a)
        if len(alerts) > 3:
            with st.expander(f"Show {len(alerts) - 3} more insight(s)"):
                for a in alerts[3:]:
                    _render_insight(a)
    else:
        st.success("✅ No unusual activity or trends detected in this window.")

# ═══════════════════════════════════════════════════════════════════════════════
# TRENDS
# ═══════════════════════════════════════════════════════════════════════════════

with t_trends:
    st.info("Charts fill in as the database accumulates weeks of history.")

    st.plotly_chart(category_share_area(_cat_share(weeks)), width='stretch', key="cat_share")
    
    st.divider()
    col_new_l, col_new_r = st.columns(2)
    with col_new_l:
        st.plotly_chart(salary_percentile_bands(_salary_percentiles(weeks)), width='stretch', key="salary_percentile_bands")
    with col_new_r:
        st.plotly_chart(seasonal_heatmap(_seasonal_heatmap()), width='stretch', key="seasonal_heatmap")

    st.divider()

    col_l, col_r = st.columns(2)
    with col_l:
        st.plotly_chart(seasonal_bar(_monthly(max(months, 3))), width='stretch', key="seasonal")
    with col_r:
        st.plotly_chart(salary_inflation_line(_salary_month(max(months, 3))), width='stretch', key="salary_inflation")

    st.divider()
    st.plotly_chart(salary_transparency_line(_salary_transparency(weeks)), width='stretch', key="salary_transparency")
    st.caption("Share of new postings that don't state a parseable salary.")

    st.divider()
    st.caption("Closing date, contract type, and hours come from detail-page enrichment — they populate as jobs are enriched.")

    col_l2, col_r2, col_c2 = st.columns(3)
    with col_l2:
        st.plotly_chart(contract_type_bar(_contract_trend(weeks)), width='stretch', key="contract_type")
    with col_r2:
        st.plotly_chart(permanent_ratio_line(_contract_trend(weeks)), width='stretch', key="permanent_ratio")
    with col_c2:
        st.plotly_chart(hours_bar(_hours_trend(weeks)), width='stretch', key="hours")

    st.divider()
    st.plotly_chart(recruitment_window_line(_recruitment_window(weeks)), width='stretch', key="recruitment_window")

# ═══════════════════════════════════════════════════════════════════════════════
# ROLES
# ═══════════════════════════════════════════════════════════════════════════════

with t_roles:
    col_sen, col_dist = st.columns(2)
    with col_sen:
        st.plotly_chart(seniority_breakdown_bar(_seniority(max(lookback_days, 365))), width='stretch', key="seniority")
        st.caption("Seniority inferred from title keywords; hover a bar for the median salary floor.")
    with col_dist:
        st.plotly_chart(salary_distribution_hist(_salary_dist(lookback_days)), width='stretch', key="salary_dist")

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.plotly_chart(
            title_frequency_bar(_title_freq(lookback_days)),
            width='stretch',
            key="title_freq",
        )

    with col_r:
        st.plotly_chart(category_growth_bar(_cat_growth()), width='stretch', key="cat_growth")

        growth = _cat_growth()
        if growth:
            df_g = pd.DataFrame(growth)
            df_g["category"] = df_g["category"].map(lambda s: CATEGORY_LABELS.get(s, s))
            df_g = df_g.rename(columns={
                "category": "Category", "last_week": "Last week",
                "this_week": "This week", "change_pct": "Change %",
            })
            st.dataframe(df_g, hide_index=True, width='stretch')

    st.divider()

    col_l2, col_r2 = st.columns(2)
    with col_l2:
        st.plotly_chart(salary_box_by_category(_salary_trends(weeks)), width='stretch', key="salary_box")
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
                hide_index=True, width='stretch',
            )

    st.divider()
    st.subheader("Keyword Salary Premium Analysis")
    st.caption("How much salary premium specific keywords in job titles command compared to their category baseline average.")
    st.plotly_chart(keyword_premium_bar(_keyword_premiums(lookback_days)), width='stretch', key="keyword_premiums")

# ═══════════════════════════════════════════════════════════════════════════════
# INSTITUTIONS
# ═══════════════════════════════════════════════════════════════════════════════

with t_institutions:
    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.plotly_chart(
            top_institutions_bar(_top_inst(lookback_days), lookback_days),
            width='stretch',
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
            st.dataframe(df_sp, hide_index=True, width='stretch')
        else:
            st.info("No spikes detected in this window.")

    st.divider()
    st.subheader("Geography")
    col_geo_l, col_geo_r = st.columns(2)
    with col_geo_l:
        st.plotly_chart(region_bar(_region(lookback_days)), width='stretch', key="region")
    with col_geo_r:
        st.plotly_chart(top_locations_bar(_top_locations(lookback_days)), width='stretch', key="top_locations")
    st.caption("Location is parsed from each job's detail page; it fills in as enrichment runs.")

    st.divider()

    col_l2, col_r2 = st.columns(2)
    with col_l2:
        st.plotly_chart(
            institution_salary_scatter(_salary_inst(lookback_days)),
            width='stretch',
            key="inst_salary",
        )
    with col_r2:
        st.plotly_chart(market_concentration_line(_market_concentration(weeks)), width='stretch', key="market_hhi")

    st.divider()

    col_l3, col_r3 = st.columns(2)
    with col_l3:
        st.plotly_chart(new_vs_repeat_bar(_new_vs_repeat(weeks)), width='stretch', key="new_vs_repeat")
    with col_r3:
        st.plotly_chart(longevity_histogram(_longevity()), width='stretch', key="longevity")
        st.caption(
            "Days visible = gap between first and last time a job appeared in "
            "the RSS feed. Zero means seen in one scrape only. This is a proxy "
            "for listing duration, not exact close date."
        )

    st.divider()
    st.subheader("Institution drill-down")
    all_jobs = _all_jobs()
    institutions = sorted(
        {j["institution"] for j in all_jobs if j["institution"]}, key=str.lower
    )
    selected = st.selectbox("Select an institution", institutions)
    if selected:
        col_drill_l, col_drill_r = st.columns(2)
        with col_drill_l:
            trend = institution_weekly_trend(selected, weeks=weeks)
            if trend:
                df_t = pd.DataFrame(trend)
                fig = px.bar(
                    df_t, x="week", y="job_count",
                    labels={"week": "ISO week", "job_count": "Jobs"},
                    title=f"{selected} — weekly postings",
                )
                st.plotly_chart(fig, width='stretch', key="inst_drill")
        with col_drill_r:
            breakdown = institution_category_breakdown(days=lookback_days)
            inst_rows = [r for r in breakdown if r["institution"] == selected]
            if inst_rows:
                df_b = pd.DataFrame(inst_rows)[["category", "job_count"]]
                df_b["category"] = df_b["category"].map(lambda s: CATEGORY_LABELS.get(s, s))
                df_b.columns = ["Category", "Jobs"]
                st.dataframe(df_b, hide_index=True, width='stretch')

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
            df_display, hide_index=True, width='stretch',
            column_config={"URL": st.column_config.LinkColumn("URL", display_text="Open")},
        )

        csv = df_filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download as CSV", data=csv,
            file_name="he_jobs_export.csv", mime="text/csv",
        )
