"""Streamlit dashboard for HE job market analysis.

Run with:
    streamlit run dashboard/app.py

Layout (September 2026 review): every windowed chart keys off the advert's true
posting date; weekly series show the full history of COMPLETE weeks and ignore
the lookback control, which scopes only the cross-sectional charts; the
headline numbers are stated as levels, not five-point trends.
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
    salary_by_institution,
    spike_candidates,
    top_institutions,
)
from analysis.trends import (
    application_window_by_discipline,
    application_window_distribution,
    attribution_counts,
    category_share_over_time,
    category_weekly_counts,
    contract_hours_matrix,
    contract_type_trend,
    daily_postings_trend,
    data_coverage,
    deadline_urgency_buckets,
    headline_stats,
    hours_trend,
    international_destinations,
    intl_vs_uk_profile,
    jobs_by_region,
    most_reposted_roles,
    nonacademic_breakdown,
    postings_by_weekday,
    recruitment_mix_by_discipline,
    region_category_matrix,
    salary_by_contract_type,
    salary_by_discipline,
    salary_by_region,
    salary_disclosure_by_group,
    salary_distribution,
    scraper_health,
    seniority_breakdown,
    seniority_salary_ladder,
    subdiscipline_breakdown,
    top_locations,
    upcoming_deadlines,
)
from config import CATEGORY_LABELS
from dashboard.charts import (
    application_window_by_discipline_bar,
    application_window_hist,
    attribution_dumbbell,
    category_label,
    category_share_area,
    category_weekly_bar,
    contract_type_bar,
    deadline_pressure_bar,
    hours_bar,
    institution_salary_scatter,
    international_destinations_bar,
    intl_vs_uk_profile_bars,
    most_reposted_bar,
    posting_volume_line,
    precarity_matrix_heatmap,
    precarity_mix_bar,
    recruiter_concentration_curve,
    region_bar,
    region_category_heatmap,
    salary_by_contract_bar,
    salary_by_discipline_bar,
    salary_by_region_bar,
    salary_distribution_hist,
    salary_transparency_breakdown,
    seniority_breakdown_bar,
    seniority_salary_ladder_bar,
    tag_breakdown_bar,
    top_institutions_bar,
    top_locations_bar,
    upcoming_deadlines_bar,
    weekday_cadence_bar,
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
        lookback_days = st.slider("Lookback window (days)", 7, 180, 90, step=7)
        st.caption("Scopes the cross-sectional charts. Weekly series always show "
                   "the full history of complete weeks. Charts cache for 5 minutes.")
with _head_left:
    st.title("HE Job Market Analysis")
    _last = last_scrape_time()
    _scraped = f" · last scraped {_last[:16]} UTC" if _last else ""
    st.caption(
        f"Data sourced from jobs.ac.uk · refreshes daily at 07:00{_scraped} · "
        f"**cross-sectional charts show the last {lookback_days} days** by posting date "
        f"(⚙ Filters to change)"
    )

with st.expander("ℹ️ How adverts are counted", expanded=False):
    st.markdown(
        "Adverts are collected daily from jobs.ac.uk search results and grouped by "
        "**subject discipline**. An advert can carry several disciplines (44% do), and "
        "it counts under **each** of them, so discipline totals add up to more than "
        "the number of adverts — see the Data tab for why. Every date is the advert's "
        "true posting date. Weekly charts exclude the current, unfinished week. "
        "PhD studentships are excluded from fixed-term shares: they are training "
        "places, not jobs, and are fixed-term by nature."
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
# Weekly series take no window argument: they always show every complete week.
# Cross-sectional loaders take the lookback, floored where a structural pattern
# needs a minimum sample (max(d, N)).

@st.cache_data(ttl=300)
def _headline():            return headline_stats(days=90)

@st.cache_data(ttl=300)
def _alerts():              return check_all()

@st.cache_data(ttl=300)
def _posting_volume(d):     return daily_postings_trend(days=d)

@st.cache_data(ttl=300)
def _cat_weekly():          return category_weekly_counts()

@st.cache_data(ttl=300)
def _cat_share():           return category_share_over_time()

@st.cache_data(ttl=300)
def _contract_trend():      return contract_type_trend()

@st.cache_data(ttl=300)
def _hours_trend():         return hours_trend()

@st.cache_data(ttl=300)
def _weekday_cadence(d):    return postings_by_weekday(days=max(d, 120))

@st.cache_data(ttl=300)
def _salary_dist(d):        return salary_distribution(days=d)

@st.cache_data(ttl=300)
def _salary_contract(d):    return salary_by_contract_type(days=max(d, 90))

@st.cache_data(ttl=300)
def _salary_disc(d):        return salary_by_discipline(days=max(d, 180), min_n=20)

@st.cache_data(ttl=300)
def _pay_ladder(d):         return seniority_salary_ladder(days=max(d, 365), min_n=15)

@st.cache_data(ttl=300)
def _salary_disclosure_groups(d): return salary_disclosure_by_group(days=max(d, 120))

@st.cache_data(ttl=300)
def _salary_region(d):      return salary_by_region(days=max(d, 90))

@st.cache_data(ttl=300)
def _recruitment_mix(d):    return recruitment_mix_by_discipline(days=max(d, 180), min_n=40)

@st.cache_data(ttl=300)
def _contract_hours_matrix(d): return contract_hours_matrix(days=max(d, 90))

@st.cache_data(ttl=300)
def _app_window(d):         return application_window_distribution(days=d)

@st.cache_data(ttl=300)
def _app_window_by_disc(d): return application_window_by_discipline(days=max(d, 90))

@st.cache_data(ttl=300)
def _deadlines():           return upcoming_deadlines(weeks_ahead=8)

@st.cache_data(ttl=300)
def _deadline_pressure():   return deadline_urgency_buckets()

@st.cache_data(ttl=300)
def _seniority(d):          return seniority_breakdown(days=max(d, 365))

@st.cache_data(ttl=300)
def _subdisciplines(slug, d): return subdiscipline_breakdown(slug, days=max(d, 180))

@st.cache_data(ttl=300)
def _nonacademic(d):        return nonacademic_breakdown(days=max(d, 180))

@st.cache_data(ttl=300)
def _top_inst(d):           return top_institutions(days=d, limit=20)

@st.cache_data(ttl=300)
def _spikes(d):             return spike_candidates(days=min(d, 30), threshold=3)

@st.cache_data(ttl=300)
def _salary_inst(d):        return salary_by_institution(days=d, min_jobs=2)

@st.cache_data(ttl=300)
def _inst_distribution(d):  return institution_posting_distribution(days=max(d, 120))

@st.cache_data(ttl=300)
def _reposted(d):           return most_reposted_roles(days=max(d, 180), limit=15)

@st.cache_data(ttl=300)
def _region(d):             return jobs_by_region(days=d)

@st.cache_data(ttl=300)
def _top_locations(d):      return top_locations(days=d, limit=15)

@st.cache_data(ttl=300)
def _region_matrix(d):      return region_category_matrix(days=d)

@st.cache_data(ttl=300)
def _intl_vs_uk(d):         return intl_vs_uk_profile(days=max(d, 120))

@st.cache_data(ttl=300)
def _intl_destinations(d):  return international_destinations(days=max(d, 120), limit=15)

@st.cache_data(ttl=300)
def _all_jobs():            return get_all_jobs()

@st.cache_data(ttl=300)
def _scraper_health():      return scraper_health(hours=24)

@st.cache_data(ttl=300)
def _coverage():            return data_coverage()

@st.cache_data(ttl=300)
def _attribution():         return attribution_counts()

# ── Tabs ──────────────────────────────────────────────────────────────────────

t_overview, t_trends, t_pay, t_contracts, t_roles, t_institutions, t_data = st.tabs(
    ["Overview", "Trends", "Pay", "Contracts & Timing", "Roles", "Institutions", "Data"]
)

# ═══════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

with t_overview:
    st.caption(
        "The market at a glance. **Trends** has the weekly history, **Pay** the salary "
        "picture, **Contracts & Timing** precarity and deadlines, **Roles** seniority and "
        "sub-discipline drill-downs, **Institutions** recruiters and geography, and "
        "**Data** the coverage figures and the raw table."
    )
    h = _headline()
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Adverts collected", f"{h['total_jobs']:,}")
    _delta = (h["last_week"] - h["prev_week"]) if h["prev_week"] is not None else None
    k2.metric(f"Last complete week ({h['last_week_label'] or '—'})", f"{h['last_week']:,}",
              delta=f"{_delta:+d} vs previous week" if _delta is not None else None)
    k3.metric("Median days to apply", f"{h['median_window_days']} d" if h["median_window_days"] is not None else "—")
    k4.metric("Adverts hiding pay", f"{h['hidden_pay_pct']:.0f}%" if h["hidden_pay_pct"] is not None else "—")
    k5.metric("Permanent share", f"{h['permanent_pct']:.0f}%" if h["permanent_pct"] is not None else "—")
    k6.metric("Institutions recruiting", f"{h['institutions']:,}")
    st.caption(f"Rates over the last {h['window_days']} days of postings ({h['n_recent']:,} adverts); "
               "permanent share excludes PhD studentships. The week-on-week figure compares the last "
               "two complete weeks.")

    st.divider()
    st.plotly_chart(posting_volume_line(_posting_volume(max(lookback_days, 120))), width='stretch', key="posting_volume")
    st.caption("Postings per day by true posting date. The shaded left edge undercounts (short-window "
               "adverts had closed before the first scrape); the last day or two is provisional.")

    col_l, col_r = st.columns(2)
    with col_l:
        st.plotly_chart(category_weekly_bar(_cat_weekly()), width='stretch', key="cat_weekly")
        st.caption("Every complete week since collection began. A multi-discipline advert counts under each discipline.")
    with col_r:
        st.plotly_chart(weekday_cadence_bar(_weekday_cadence(lookback_days)), width='stretch', key="weekday_cadence")
        st.caption("Which weekday adverts are published on. Universities publish on working days.")

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
            st.info(f"{m['icon']} **{m['label']}** — {a.message}")

        for a in alerts[:3]:
            _render_insight(a)
        if len(alerts) > 3:
            with st.expander(f"Show {len(alerts) - 3} more insight(s)"):
                for a in alerts[3:]:
                    _render_insight(a)
        st.caption("Week-on-week changes compare the last two complete weeks; spikes are the last 7 days.")
    else:
        st.success("✅ No unusual activity or trends detected.")

# ═══════════════════════════════════════════════════════════════════════════════
# TRENDS
# ═══════════════════════════════════════════════════════════════════════════════

with t_trends:
    st.caption(
        "The full weekly history, complete weeks only, by true posting date. The lookback "
        "control does not apply here. Over one spring and summer these are mostly flat; "
        "seasonality needs a full year and will appear here when there is one."
    )
    st.plotly_chart(category_share_area(_cat_share()), width='stretch', key="cat_share")
    st.caption("Share of discipline tags per week (an advert with several disciplines contributes to each).")
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.plotly_chart(contract_type_bar(_contract_trend()), width='stretch', key="contract_type")
    with col_t2:
        st.plotly_chart(hours_bar(_hours_trend()), width='stretch', key="hours")
    st.caption("Contract type and hours come from each advert's detail page (97% coverage).")

# ═══════════════════════════════════════════════════════════════════════════════
# PAY
# ═══════════════════════════════════════════════════════════════════════════════

with t_pay:
    st.caption(
        "Advertised salary floors. Adverts quote national spine points, so the distribution is "
        "spiky and month-to-month movement is not meaningful; these are cross-sections over "
        f"the last {lookback_days} days (or longer where a floor is noted)."
    )
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.plotly_chart(salary_distribution_hist(_salary_dist(lookback_days)), width='stretch', key="salary_dist")
    with col_p2:
        st.plotly_chart(salary_by_contract_bar(_salary_contract(lookback_days)), width='stretch', key="salary_contract")
        st.caption("Median advertised salary floor for permanent vs fixed-term roles (at least 90 days).")

    st.plotly_chart(salary_by_discipline_bar(_salary_disc(lookback_days)), width='stretch', key="salary_by_discipline")
    st.caption("Median full-time salary floor per discipline over at least 180 days, with the p25–p75 spread "
               "as a whisker; disciplines need 20+ salaried full-time adverts. Hover for the figures.")

    st.plotly_chart(seniority_salary_ladder_bar(_pay_ladder(lookback_days)), width='stretch', key="pay_ladder")
    st.caption(
        "The academic pay ladder: median advertised salary floor per seniority band, with the "
        "25th–75th percentile whisker. Full-time roles only, since part-time adverts quote FTE "
        "and pro-rata figures inconsistently. Uses at least 12 months so thin senior bands have a sample."
    )

    col_p3, col_p4 = st.columns(2)
    with col_p3:
        st.plotly_chart(salary_transparency_breakdown(_salary_disclosure_groups(lookback_days)), width='stretch', key="salary_transparency_breakdown")
        st.caption("Share of adverts with no parseable salary, by discipline and by region, against the overall "
                   "baseline. International reads near 100% because non-GBP pay never parses.")
    with col_p4:
        st.plotly_chart(salary_by_region_bar(_salary_region(lookback_days)), width='stretch', key="salary_region")
        st.caption("UK nations only. International pay is converted foreign currency with under half disclosed, "
                   "so a £ median would not be comparable.")

# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACTS & TIMING
# ═══════════════════════════════════════════════════════════════════════════════

with t_contracts:
    st.caption("How precarious the advertised posts are, and how long applicants get.")
    st.plotly_chart(precarity_mix_bar(_recruitment_mix(lookback_days)), width='stretch', key="precarity_mix")
    st.caption("Fixed-term share of contracted adverts per discipline (at least 180 days; disciplines with 40+ "
               "contracted adverts; PhD studentships excluded) against the all-adverts line, coloured by what "
               "each discipline is hiring: research posts (research fellow/associate/assistant, postdoc) versus "
               "lecturer posts, classified from titles. Research-heavy disciplines cluster at the top because "
               "research posts are almost all fixed-term; a balanced or teaching-heavy discipline sitting high is "
               "teaching on temporary contracts. Hover for the research-posts-per-lecturer-post ratio.")
    st.plotly_chart(precarity_matrix_heatmap(_contract_hours_matrix(lookback_days)), width='stretch', key="precarity_matrix")
    st.caption("Adverts by contract type × hours (share of the enriched subset). The outlined cell is the "
               "doubly-precarious fixed-term + part-time corner.")

    st.divider()
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.plotly_chart(application_window_hist(_app_window(lookback_days)), width='stretch', key="app_window")
    with col_c2:
        st.plotly_chart(application_window_by_discipline_bar(_app_window_by_disc(lookback_days)), width='stretch', key="app_window_by_disc")
        st.caption("Median application window (closing − posting date) per discipline with the p25–p75 spread; "
                   "the dashed line is the market median. Disciplines need at least 10 dated adverts.")
    col_c3, col_c4 = st.columns(2)
    with col_c3:
        st.plotly_chart(upcoming_deadlines_bar(_deadlines()), width='stretch', key="deadlines")
        st.caption("Currently open adverts by the week their deadline falls.")
    with col_c4:
        _dl_buckets = _deadline_pressure()
        st.plotly_chart(deadline_pressure_bar(_dl_buckets), width='stretch', key="deadline_pressure")
        _urgent_72h = next((b["job_count"] for b in _dl_buckets if b["bucket"] == "0-3"), 0)
        st.caption(f"{_urgent_72h:,} open advert(s) close within 72 hours.")

# ═══════════════════════════════════════════════════════════════════════════════
# ROLES
# ═══════════════════════════════════════════════════════════════════════════════

with t_roles:
    st.caption("What is being hired: seniority bands from titles, then the sub-discipline and "
               "professional-services tags that each advert's page carries.")
    st.plotly_chart(seniority_breakdown_bar(_seniority(lookback_days)), width='stretch', key="seniority")
    st.caption("Seniority inferred from title keywords over at least 12 months; hover a bar for the median "
               "salary floor. Titles that match no band are shown as Other / Unclassified.")

    st.divider()
    st.subheader("Sub-discipline drill-down")
    _disc_slug = st.selectbox("Discipline", options=list(CATEGORY_LABELS.keys()),
                              format_func=category_label, index=list(CATEGORY_LABELS).index("computer-sciences"))
    _subs = _subdisciplines(_disc_slug, lookback_days)
    col_r1, col_r2 = st.columns([3, 2])
    with col_r1:
        st.plotly_chart(tag_breakdown_bar(_subs, f"Sub-disciplines within {category_label(_disc_slug)}"),
                        width='stretch', key="subdisciplines")
    with col_r2:
        if _subs:
            df_sub = pd.DataFrame(_subs)[["name", "n", "fixed_term_pct", "median_salary"]].rename(columns={
                "name": "Sub-discipline", "n": "Adverts", "fixed_term_pct": "Fixed-term %",
                "median_salary": "Median floor (£, full-time)"})
            st.dataframe(df_sub, hide_index=True, width='stretch')
    st.caption("Sub-discipline tags are read from each advert's page (at least 180 days; tags with 5+ adverts). "
               "An advert can carry several, so the counts overlap. Fixed-term share excludes PhD studentships; "
               "median pay needs 5+ salaried full-time adverts.")

    st.divider()
    st.plotly_chart(tag_breakdown_bar(_nonacademic(lookback_days), "Professional services areas"),
                    width='stretch', key="nonacademic")
    st.caption("Non-academic areas the site tags adverts with — the professional-services jobs that discipline "
               "charts cannot see (at least 180 days). An advert can carry both an academic discipline and one of these.")

# ═══════════════════════════════════════════════════════════════════════════════
# INSTITUTIONS
# ═══════════════════════════════════════════════════════════════════════════════

with t_institutions:
    st.caption(
        "Who is recruiting and where — **Recruiters** (top employers, spikes, drill-down, "
        "concentration, pay vs volume, reposts) · **Geography** (nations, cities, international)."
    )
    sub_recruiters, sub_geography = st.tabs(["Recruiters", "Geography"])

    with sub_recruiters:
        col_l, col_r = st.columns([3, 2])
        with col_l:
            st.plotly_chart(top_institutions_bar(_top_inst(lookback_days), lookback_days),
                            width='stretch', key="top_inst")
        with col_r:
            st.subheader("Spike watch (last 7 days, >= 3 jobs)")
            spikes = _spikes(lookback_days)
            if spikes:
                df_sp = pd.DataFrame(spikes)[["institution", "job_count", "category_list"]]
                df_sp["category_list"] = df_sp["category_list"].apply(
                    lambda s: ", ".join(category_label(c.strip()) for c in s.split(",")))
                df_sp.columns = ["Institution", "Jobs", "Disciplines"]
                st.dataframe(df_sp, hide_index=True, width='stretch')
            else:
                st.info("No spikes detected in this window.")

        st.divider()
        st.subheader("Institution drill-down")
        all_jobs = _all_jobs()
        institutions = sorted({j["institution"] for j in all_jobs if j["institution"]}, key=str.lower)
        selected = st.selectbox("Select an institution", institutions)
        if selected:
            col_drill_l, col_drill_r = st.columns(2)
            with col_drill_l:
                trend = institution_weekly_trend(selected, weeks=52)
                if trend:
                    df_t = pd.DataFrame(trend)
                    fig = px.bar(df_t, x="week", y="job_count",
                                 labels={"week": "ISO week", "job_count": "Adverts"},
                                 title=f"{selected} — adverts per complete week")
                    st.plotly_chart(fig, width='stretch', key="inst_drill")
            with col_drill_r:
                breakdown = institution_category_breakdown(days=lookback_days)
                inst_rows = [r for r in breakdown if r["institution"] == selected]
                if inst_rows:
                    df_b = pd.DataFrame(inst_rows)[["category", "job_count"]]
                    df_b["category"] = df_b["category"].map(category_label)
                    df_b.columns = ["Discipline", "Adverts"]
                    st.dataframe(df_b, hide_index=True, width='stretch')

        st.divider()
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            st.plotly_chart(recruiter_concentration_curve(_inst_distribution(lookback_days)), width='stretch', key="recruiter_concentration")
            st.caption("Lorenz curve over at least 120 days. The further the curve sags below the diagonal, "
                       "the more a few institutions dominate hiring.")
        with col_i2:
            st.plotly_chart(institution_salary_scatter(_salary_inst(lookback_days)), width='stretch', key="inst_salary")
        st.plotly_chart(most_reposted_bar(_reposted(lookback_days)), width='stretch', key="most_reposted")
        st.caption("Same title advertised repeatedly by the same institution over at least 6 months — hard-to-fill "
                   "posts or rolling recruitment. Titles match exactly, so near-duplicates are under-counted.")

    with sub_geography:
        col_geo_l, col_geo_r = st.columns(2)
        with col_geo_l:
            st.plotly_chart(region_bar(_region(lookback_days)), width='stretch', key="region")
        with col_geo_r:
            st.plotly_chart(top_locations_bar(_top_locations(lookback_days)), width='stretch', key="top_locations")
        st.plotly_chart(region_category_heatmap(_region_matrix(lookback_days)), width='stretch', key="region_category")
        st.caption("Location and region are parsed from each advert's detail page.")
        st.plotly_chart(intl_vs_uk_profile_bars(_intl_vs_uk(lookback_days)), width='stretch', key="intl_vs_uk_profile")
        st.caption("How International and UK adverts differ in structure, as shares. Only the salary-disclosure "
                   "rate is compared, never a £ value, because International pay is non-GBP.")
        st.plotly_chart(international_destinations_bar(_intl_destinations(lookback_days)), width='stretch', key="intl_destinations")
        st.caption("International adverts by city, over at least 4 months.")

# ═══════════════════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════════════════

with t_data:
    st.caption("How much of the data is filled in, why discipline counts overlap, and every advert behind the charts.")

    # ── Scraper health and coverage ───────────────────────────────────────────
    _health = _scraper_health()
    _cov = _coverage()
    if _health["last_run_at"]:
        ok = _health["last_status"] == "ok" and _health["errors"] == 0
        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Last scrape (UTC)", _health["last_run_at"][:16])
        h2.metric("Status", "✅ Healthy" if ok else "⚠️ Errors")
        h3.metric("New adverts (24h)", f"{_health['new_jobs']:,}")
        h4.metric("Runs (24h)", f"{_health['runs']} · {_health['errors']} err")
        if not ok and _health["last_error"]:
            le = _health["last_error"]
            st.warning(f"Most recent scrape error — {le['run_at'][:16]} UTC on "
                       f"**{category_label(le['category'])}**: {le['error']}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Contract type known", f"{_cov['contract_pct']:.0f}%")
    c2.metric("Salary parsed", f"{_cov['salary_pct']:.0f}%")
    c3.metric("Region known", f"{_cov['region_pct']:.0f}%")
    c4.metric("Disciplines captured", f"{_cov['disciplines_pct']:.0f}%")
    c5.metric("Multi-discipline adverts", f"{_cov['multi_discipline_pct']:.0f}%")
    st.caption(f"{_cov['total']:,} adverts posted {_cov['posted_min']} to {_cov['posted_max']}. "
               "Fill rates are over every advert collected; each chart states its own sample floor.")

    st.divider()
    st.plotly_chart(attribution_dumbbell(_attribution()), width='stretch', key="attribution")
    st.caption("Why discipline counts add up to more than the advert total. The light dot counts each advert once, "
               "under the first subject listed on its page; the dark dot counts it under every subject it carries. "
               "The site lists subjects in a fixed order, so any single-label rule undercounts whichever "
               "subjects come later — the dashboard counts every subject.")

    st.divider()
    all_jobs = _all_jobs()
    df_all = pd.DataFrame(all_jobs)

    if df_all.empty:
        st.info("No data in database yet. Run the scraper first.")
    else:
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            cat_filter = st.multiselect("Discipline", options=list(CATEGORY_LABELS.keys()),
                                        format_func=category_label)
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
        st.caption(f"Showing {len(df_filtered):,} of {len(df_all):,} adverts")

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
