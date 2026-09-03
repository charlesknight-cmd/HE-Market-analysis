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
    institution_posting_distribution,
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
    application_window_distribution,
    upcoming_deadlines,
    salary_by_region,
    salary_by_contract_type,
    region_category_matrix,
    daily_postings_trend,
    postings_by_weekday,
    salary_disclosure_by_group,
    intl_vs_uk_profile,
    fixed_term_share_by_discipline,
    recruitment_mix_by_discipline,
    application_window_by_discipline,
    contract_hours_matrix,
    deadline_urgency_buckets,
    most_reposted_roles,
    international_destinations,
    scraper_health,
    seniority_salary_ladder,
)
from config import CATEGORY_LABELS
from dashboard.charts import (
    category_label,
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
    application_window_hist,
    upcoming_deadlines_bar,
    salary_by_region_bar,
    salary_by_contract_bar,
    region_category_heatmap,
    region_choropleth,
    posting_volume_line,
    weekday_cadence_bar,
    recruiter_concentration_curve,
    salary_transparency_breakdown,
    intl_vs_uk_profile_bars,
    casualisation_by_discipline_bar,
    precarity_mix_bar,
    application_window_by_discipline_bar,
    precarity_matrix_heatmap,
    deadline_pressure_bar,
    most_reposted_bar,
    international_destinations_bar,
    seniority_salary_ladder_bar,
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

# st.secrets raises StreamlitSecretNotFoundError (not KeyError) when no
# secrets.toml exists at all, so `.get(..., "")` does NOT fall back to the
# default — it propagates and crashes the whole app on startup. Guard it so a
# missing secrets file simply means "no password gate" (e.g. local dev).
try:
    _required_pwd = st.secrets.get("password", "")
except Exception:
    _required_pwd = ""
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
# Render the filters popover first so the active lookback is known when we build
# the header caption — that way the current window is always visible without
# opening the popover. (Column display order is fixed by the columns list, not by
# the order of these `with` blocks.)
with _head_right:
    with st.popover("⚙ Filters", width="stretch"):
        lookback_days = st.slider("Lookback window (days)", 7, 180, 30, step=7)
        st.caption("Charts cache for 5 minutes")
with _head_left:
    st.title("HE Job Market Analysis")
    _last = last_scrape_time()
    _scraped = f" · last scraped {_last[:16]} UTC" if _last else ""
    st.caption(
        f"Data sourced from jobs.ac.uk · refreshes daily at 07:00{_scraped} · "
        f"**showing last {lookback_days} days** (⚙ Filters to change)"
    )

# Site-change note for users (June 2026 source/taxonomy migration).
with st.expander("ℹ️ Update — June 2026: how jobs are categorised has changed", expanded=False):
    st.markdown(
        "jobs.ac.uk changed how it publishes listings, so this tool now collects "
        "data directly from their search results and groups roles by **subject "
        "discipline** (e.g. Computer Sciences, Health & Medical, Engineering & "
        "Technology) rather than the previous job-type categories. Coverage and "
        "salary/location data are unchanged or improved. A small number of older "
        "listings may still show the previous categories until they expire."
    )

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
        transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1),
                    box-shadow 0.3s cubic-bezier(0.25, 0.8, 0.25, 1),
                    border-color 0.3s ease, background 0.3s ease;
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
        transition: background-color 0.2s ease, color 0.2s ease;
    }

    /* Active tab styling */
    button[aria-selected="true"] {
        background-color: rgba(76, 114, 176, 0.08) !important;
        color: #4C72B0 !important;
    }

    /* Respect reduced-motion: drop the hover lift and transitions. */
    @media (prefers-reduced-motion: reduce) {
        div[data-testid="stMetric"],
        button[data-baseweb="tab"] {
            transition: none;
        }
        div[data-testid="stMetric"]:hover {
            transform: none;
        }
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

@st.cache_data(ttl=300)
def _app_window(d):         return application_window_distribution(days=d)

@st.cache_data(ttl=300)
def _deadlines():           return upcoming_deadlines(weeks_ahead=8)

@st.cache_data(ttl=300)
def _salary_region(d):      return salary_by_region(days=max(d, 90))

@st.cache_data(ttl=300)
def _salary_contract(d):    return salary_by_contract_type(days=max(d, 90))

@st.cache_data(ttl=300)
def _region_matrix(d):      return region_category_matrix(days=d)

# New charts (2026-06): exploit the now ~3-month date_posted history + enriched
# fields. Several floor their window (max(d, N)) so structural patterns still
# render when the sidebar lookback is short.
@st.cache_data(ttl=300)
def _posting_volume(d):     return daily_postings_trend(days=d)

@st.cache_data(ttl=300)
def _weekday_cadence(d):    return postings_by_weekday(days=max(d, 120))

@st.cache_data(ttl=300)
def _inst_distribution(d):  return institution_posting_distribution(days=max(d, 120))

@st.cache_data(ttl=300)
def _salary_disclosure_groups(d): return salary_disclosure_by_group(days=max(d, 120))

@st.cache_data(ttl=300)
def _intl_vs_uk(d):         return intl_vs_uk_profile(days=max(d, 120))

@st.cache_data(ttl=300)
def _casualisation(d):      return fixed_term_share_by_discipline(days=max(d, 180), min_n=40)
@st.cache_data(ttl=300)
def _recruitment_mix(d):    return recruitment_mix_by_discipline(days=max(d, 180), min_n=40)

@st.cache_data(ttl=300)
def _app_window_by_disc(d): return application_window_by_discipline(days=max(d, 90))

@st.cache_data(ttl=300)
def _contract_hours_matrix(d): return contract_hours_matrix(days=max(d, 90))

@st.cache_data(ttl=300)
def _deadline_pressure():   return deadline_urgency_buckets()
@st.cache_data(ttl=300)
def _reposted(d):           return most_reposted_roles(days=max(d, 180), limit=15)
@st.cache_data(ttl=300)
def _intl_destinations(d):  return international_destinations(days=max(d, 120), limit=15)
@st.cache_data(ttl=300)
def _scraper_health():      return scraper_health(hours=24)
@st.cache_data(ttl=300)
def _pay_ladder(d):         return seniority_salary_ladder(days=max(d, 365), min_n=15)

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
    st.caption(
        "At-a-glance market health. Go deeper in **Trends** (volume · pay · "
        "contracts · timing), **Roles** (seniority · salaries), **Institutions** "
        "(recruiters · geography · dynamics) and **Data** (the raw, exportable table)."
    )
    summary = _summary()
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total jobs", f"{summary['total_jobs']:,}")
    k2.metric("New (7 days)", f"{summary['new_7d']:,}")
    k3.metric("New (30 days)", f"{summary['new_30d']:,}")
    k4.metric("Institutions", f"{summary['institutions']:,}")
    k5.metric("Disciplines", summary["categories"])

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
            # Messages are already humanised at the source (analysis/alerts.py uses
            # discipline_label), so no slug-substitution pass is needed here — and
            # skipping it avoids ever mangling a hyphenated institution name.
            st.info(f"{m['icon']} **{m['label']}** — {a.message}")

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
    st.caption(
        "How the market moves over time — sub-tabs: **Volume & Seasonality** · "
        "**Pay** · **Contracts** · **Timing**. Charts fill in as the database "
        "accumulates weeks of history."
    )
    sub_volume, sub_pay, sub_contract, sub_timing = st.tabs(
        ["Volume & Seasonality", "Pay", "Contracts", "Timing"]
    )

    with sub_volume:
        st.plotly_chart(posting_volume_line(_posting_volume(max(lookback_days, 120))), width='stretch', key="posting_volume")
        st.caption("Postings counted by their true publication date (date_posted) over the last ~3 months. The "
                   "shaded left edge undercounts (short-window jobs may have closed before our first scrape); "
                   "the last day or two is still provisional.")
        st.plotly_chart(category_share_area(_cat_share(weeks)), width='stretch', key="cat_share")
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            st.plotly_chart(seasonal_heatmap(_seasonal_heatmap()), width='stretch', key="seasonal_heatmap")
        with col_v2:
            st.plotly_chart(seasonal_bar(_monthly(max(months, 3))), width='stretch', key="seasonal")
        st.plotly_chart(weekday_cadence_bar(_weekday_cadence(lookback_days)), width='stretch', key="weekday_cadence")
        st.caption("Which weekday new roles are published on (true posting date). Universities publish on "
                   "working days, so weekends are effectively empty.")

    with sub_pay:
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            st.plotly_chart(salary_percentile_bands(_salary_percentiles(weeks)), width='stretch', key="salary_percentile_bands")
        with col_p2:
            st.plotly_chart(salary_inflation_line(_salary_month(max(months, 3))), width='stretch', key="salary_inflation")
        st.plotly_chart(salary_transparency_line(_salary_transparency(weeks)), width='stretch', key="salary_transparency")
        st.caption("Share of new postings that don't state a parseable salary.")
        st.plotly_chart(salary_transparency_breakdown(_salary_disclosure_groups(lookback_days)), width='stretch', key="salary_transparency_breakdown")
        st.caption("Share of postings with no parseable salary, split by discipline and by region, against the "
                   "overall baseline. International reads near 100% because its non-GBP pay never parses.")

    with sub_contract:
        st.caption("Contract type and hours come from detail-page enrichment — they populate as jobs are enriched.")
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            st.plotly_chart(contract_type_bar(_contract_trend(weeks)), width='stretch', key="contract_type")
        with col_c2:
            st.plotly_chart(permanent_ratio_line(_contract_trend(weeks)), width='stretch', key="permanent_ratio")
        with col_c3:
            st.plotly_chart(hours_bar(_hours_trend(weeks)), width='stretch', key="hours")
        st.plotly_chart(casualisation_by_discipline_bar(_casualisation(lookback_days)), width='stretch', key="casualisation")
        st.caption("Fixed-term share of contracted postings per discipline (last 180 days; disciplines with 40+ "
                   "contracted roles). Bars right of the dashed baseline are more casualised than the market.")
        st.plotly_chart(precarity_mix_bar(_recruitment_mix(lookback_days)), width='stretch', key="precarity_mix")
        st.caption("The same fixed-term shares, coloured by what each discipline is hiring: research posts "
                   "(research fellow/associate/assistant, postdoc) versus lecturer posts, classified from titles. "
                   "Research-heavy disciplines cluster at the top because research posts are almost all fixed-term; "
                   "a balanced or teaching-heavy discipline sitting high is teaching on temporary contracts. "
                   "Hover for the research-posts-per-lecturer-post ratio.")
        st.plotly_chart(precarity_matrix_heatmap(_contract_hours_matrix(lookback_days)), width='stretch', key="precarity_matrix")
        st.caption("Postings by contract-type × hours (share of the enriched subset). The outlined cell is the "
                   "doubly-precarious fixed-term + part-time corner.")

    with sub_timing:
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.plotly_chart(recruitment_window_line(_recruitment_window(weeks)), width='stretch', key="recruitment_window")
        with col_t2:
            st.plotly_chart(application_window_hist(_app_window(lookback_days)), width='stretch', key="app_window")
        st.plotly_chart(upcoming_deadlines_bar(_deadlines()), width='stretch', key="deadlines")
        st.caption("Currently-open jobs grouped by the week their application deadline falls — the recruiting pipeline ahead.")
        _dl_buckets = _deadline_pressure()
        st.plotly_chart(deadline_pressure_bar(_dl_buckets), width='stretch', key="deadline_pressure")
        _urgent_72h = next((b["job_count"] for b in _dl_buckets if b["bucket"] == "0-3"), 0)
        st.caption(f"{_urgent_72h:,} role(s) close within 72h — the most urgent end of the open-jobs pipeline.")
        st.plotly_chart(application_window_by_discipline_bar(_app_window_by_disc(lookback_days)), width='stretch', key="app_window_by_disc")
        st.caption("Median application window (closing − posting date) per discipline, with the p25–p75 spread; the "
                   "dashed line is the market-wide median. Disciplines need at least 10 dated postings to appear.")

# ═══════════════════════════════════════════════════════════════════════════════
# ROLES
# ═══════════════════════════════════════════════════════════════════════════════

with t_roles:
    st.caption(
        "What's being hired and what it pays — sub-tabs: **Role Types** "
        "(seniority, title words, growth) · **Salaries** (distribution, ranges, "
        "keyword premiums)."
    )
    sub_roletypes, sub_salaries = st.tabs(["Role Types", "Salaries"])

    with sub_roletypes:
        col_rt1, col_rt2 = st.columns(2)
        with col_rt1:
            st.plotly_chart(seniority_breakdown_bar(_seniority(max(lookback_days, 365))), width='stretch', key="seniority")
            st.caption("Seniority inferred from title keywords; hover a bar for the median salary floor.")
        with col_rt2:
            st.plotly_chart(title_frequency_bar(_title_freq(lookback_days)), width='stretch', key="title_freq")

        st.divider()
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.plotly_chart(category_growth_bar(_cat_growth()), width='stretch', key="cat_growth")
        with col_g2:
            growth = _cat_growth()
            if growth:
                df_g = pd.DataFrame(growth)
                df_g["category"] = df_g["category"].map(category_label)
                df_g = df_g.rename(columns={
                    "category": "Discipline", "last_week": "Last week",
                    "this_week": "This week", "change_pct": "Change %",
                })
                st.dataframe(df_g, hide_index=True, width='stretch')

    with sub_salaries:
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.plotly_chart(salary_distribution_hist(_salary_dist(lookback_days)), width='stretch', key="salary_dist")
        with col_s2:
            st.plotly_chart(salary_box_by_category(_salary_trends(weeks)), width='stretch', key="salary_box")

        sal = _salary_trends(weeks)
        if sal:
            df_s = pd.DataFrame(sal)
            df_s = df_s.sort_values("week").groupby("category").last().reset_index()
            df_s["category"] = df_s["category"].map(category_label)
            df_s["avg_salary_min"] = df_s["avg_salary_min"].apply(
                lambda x: f"£{x:,.0f}" if x else "—"
            )
            df_s["avg_salary_max"] = df_s["avg_salary_max"].apply(
                lambda x: f"£{x:,.0f}" if x else "—"
            )
            df_s = df_s.rename(columns={
                "category": "Discipline", "avg_salary_min": "Avg floor",
                "avg_salary_max": "Avg ceiling", "n": "Jobs with salary",
            })
            st.dataframe(
                df_s[["Discipline", "Avg floor", "Avg ceiling", "Jobs with salary"]],
                hide_index=True, width='stretch',
            )

        st.divider()
        st.plotly_chart(salary_by_contract_bar(_salary_contract(lookback_days)), width='stretch', key="salary_contract")
        st.caption("Median advertised salary floor for permanent vs fixed-term roles (contract type from enrichment).")

        st.divider()
        st.plotly_chart(seniority_salary_ladder_bar(_pay_ladder(lookback_days)), width='stretch', key="pay_ladder")
        st.caption(
            "The academic pay ladder: median advertised salary floor per seniority band, "
            "climbing from PhD stipends to professorial pay, with the whisker showing the "
            "25th–75th percentile spread within each rung. Full-time roles only — part-time "
            "adverts quote FTE and pro-rata figures inconsistently, so restricting to "
            "full-time is the honest like-for-like comparison. Uses ≥12 months so thinner "
            "senior bands have enough sample."
        )

        st.divider()
        st.subheader("Keyword Salary Premium Analysis")
        st.caption("How much salary premium specific keywords in job titles command compared to their category baseline average.")
        st.plotly_chart(keyword_premium_bar(_keyword_premiums(lookback_days)), width='stretch', key="keyword_premiums")

# ═══════════════════════════════════════════════════════════════════════════════
# INSTITUTIONS
# ═══════════════════════════════════════════════════════════════════════════════

with t_institutions:
    st.caption(
        "Who's recruiting and where — sub-tabs: **Recruiters** (top employers, "
        "spikes, drill-down) · **Geography** (map, regions, locations) · "
        "**Dynamics** (pay vs volume, concentration, churn)."
    )
    sub_recruiters, sub_geography, sub_dynamics = st.tabs(
        ["Recruiters", "Geography", "Dynamics"]
    )

    with sub_recruiters:
        col_l, col_r = st.columns([3, 2])
        with col_l:
            st.plotly_chart(
                top_institutions_bar(_top_inst(lookback_days), lookback_days),
                width='stretch', key="top_inst",
            )
        with col_r:
            st.subheader("Spike watch (last 7 days, >= 3 jobs)")
            spikes = _spikes(lookback_days)
            if spikes:
                df_sp = pd.DataFrame(spikes)[["institution", "job_count", "category_list"]]
                df_sp["category_list"] = df_sp["category_list"].apply(
                    lambda s: ", ".join(category_label(c.strip()) for c in s.split(","))
                )
                df_sp.columns = ["Institution", "Jobs", "Disciplines"]
                st.dataframe(df_sp, hide_index=True, width='stretch')
            else:
                st.info("No spikes detected in this window.")

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
                    df_b["category"] = df_b["category"].map(category_label)
                    df_b.columns = ["Discipline", "Jobs"]
                    st.dataframe(df_b, hide_index=True, width='stretch')

        st.divider()
        st.plotly_chart(recruiter_concentration_curve(_inst_distribution(lookback_days)), width='stretch', key="recruiter_concentration")
        st.caption("Lorenz curve over true posting dates (last 120 days). The dashed line is perfect equality; the "
                   "further the blue curve sags below it, the more a few institutions dominate hiring "
                   "(Gini 0 = even, 1 = one recruiter posts everything).")

    with sub_geography:
        col_geo_l, col_geo_r = st.columns(2)
        with col_geo_l:
            st.plotly_chart(region_choropleth(_region(lookback_days)), width='stretch', key="region_map")
        with col_geo_r:
            st.plotly_chart(region_bar(_region(lookback_days)), width='stretch', key="region")

        col_geo_l2, col_geo_r2 = st.columns(2)
        with col_geo_l2:
            st.plotly_chart(top_locations_bar(_top_locations(lookback_days)), width='stretch', key="top_locations")
        with col_geo_r2:
            st.plotly_chart(salary_by_region_bar(_salary_region(lookback_days)), width='stretch', key="salary_region")

        st.plotly_chart(region_category_heatmap(_region_matrix(lookback_days)), width='stretch', key="region_category")
        st.caption("Location and salary are parsed from each job's detail page. The map and bar cover UK nations; "
                   "International roles appear in the bar but not the map.")
        st.plotly_chart(intl_vs_uk_profile_bars(_intl_vs_uk(lookback_days)), width='stretch', key="intl_vs_uk_profile")
        st.caption("How International and UK postings differ in structure, shown as shares so the much larger UK "
                   "sample doesn't dominate. The salary-disclosure bar is the key gap: International pay is non-GBP "
                   "and reads as undisclosed, so only the disclosure rate is compared — never a £ value.")

        st.plotly_chart(international_destinations_bar(_intl_destinations(lookback_days)), width='stretch', key="intl_destinations")
        st.caption("The map lumps everything outside the UK into one 'International' bucket; this breaks it out by "
                   "city, from the location parsed off each detail page. Shows at least the last ~4 months so the "
                   "sample is meaningful.")

    with sub_dynamics:
        col_l2, col_r2 = st.columns(2)
        with col_l2:
            st.plotly_chart(
                institution_salary_scatter(_salary_inst(lookback_days)),
                width='stretch', key="inst_salary",
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
                "the search listings. Zero means seen in one scrape only. This is "
                "a proxy for listing duration, not exact close date."
            )

        st.divider()
        st.plotly_chart(most_reposted_bar(_reposted(lookback_days)), width='stretch', key="most_reposted")
        st.caption(
            "Same job title advertised repeatedly by the same institution over the "
            "last ~6 months — a signal of hard-to-fill posts or rolling recruitment "
            "(common for postdoc/research pools). Titles are matched exactly, so "
            "near-duplicates are under- rather than over-counted. Hover for the "
            "average application window."
        )

# ═══════════════════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════════════════

with t_data:
    st.caption(
        "Every job behind the charts — filter by discipline, institution or salary "
        "floor, then download the result as CSV."
    )

    # ── Data freshness / scraper health ───────────────────────────────────────
    # Surfaces the scrape_runs log so a silent scraper failure is visible rather
    # than looking like a genuinely quiet market. Weekends legitimately show 0
    # new jobs, so "new in 24h" is framed alongside run success, not alone.
    _health = _scraper_health()
    if _health["last_run_at"]:
        ok = _health["last_status"] == "ok" and _health["errors"] == 0
        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Last scrape (UTC)", _health["last_run_at"][:16])
        h2.metric("Status", "✅ Healthy" if ok else "⚠️ Errors")
        h3.metric("New jobs (24h)", f"{_health['new_jobs']:,}")
        h4.metric("Runs (24h)", f"{_health['runs']} · {_health['errors']} err")
        if not ok and _health["last_error"]:
            le = _health["last_error"]
            st.warning(
                f"Most recent scrape error — {le['run_at'][:16]} UTC on "
                f"**{category_label(le['category'])}**: {le['error']}"
            )
    st.divider()

    all_jobs = _all_jobs()
    df_all = pd.DataFrame(all_jobs)

    if df_all.empty:
        st.info("No data in database yet. Run the scraper first.")
    else:
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            cat_filter = st.multiselect(
                "Discipline", options=list(CATEGORY_LABELS.keys()),
                format_func=category_label,
            )
        with fc2:
            inst_search = st.text_input("Institution contains")
        with fc3:
            salary_min_filter = st.number_input("Min salary floor (£)", value=0, step=5000)

        mask = pd.Series([True] * len(df_all))
        if cat_filter:
            # `disciplines` holds every academic discipline the job is tagged
            # with (comma-joined), so a multi-discipline job matches any of them.
            wanted = set(cat_filter)
            mask &= df_all["disciplines"].fillna("").apply(
                lambda s: bool(wanted.intersection(s.split(","))))
        if inst_search:
            mask &= df_all["institution"].str.contains(inst_search, case=False, na=False)
        if salary_min_filter > 0:
            mask &= df_all["salary_min"] >= salary_min_filter

        df_filtered = df_all[mask].copy()
        st.caption(f"Showing {len(df_filtered):,} of {len(df_all):,} jobs")

        show_cols = ["title", "institution", "disciplines", "region", "salary_raw",
                     "date_posted", "closing_date", "first_seen", "url"]
        df_display = df_filtered[show_cols].rename(columns={
            "title": "Title", "institution": "Institution", "disciplines": "Discipline",
            "region": "Region", "salary_raw": "Salary", "date_posted": "Posted",
            "closing_date": "Closes", "first_seen": "First seen", "url": "URL",
        })
        df_display["Discipline"] = df_display["Discipline"].fillna("").apply(
            lambda s: ", ".join(category_label(c) for c in str(s).split(",") if c))

        st.dataframe(
            df_display, hide_index=True, width='stretch',
            column_config={"URL": st.column_config.LinkColumn("URL", display_text="Open")},
        )

        csv = df_filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download as CSV", data=csv,
            file_name="he_jobs_export.csv", mime="text/csv",
        )
