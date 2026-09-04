# Dashboard review, September 2026

Reviewed against the live database as of 3 September 2026: 7,014 adverts, posting
dates March to September, 14 weeks of daily scraping, every advert tagged with its
full set of disciplines. All 43 charts were rendered from a copy of the live data at
the dashboard's default 30-day lookback and inspected; the data behind each was
checked separately.

## Verdict

The dashboard was built before the data existed and it shows. Roughly a third of the
charts are now either wrong (they encode scraper artefacts) or empty of information
(five flat weekly points). A third are sound. The rest are fine but redundant. The
data now supports about 25 charts well; 43 dilutes them.

Three problems recur across many charts and should be fixed once, centrally, before
anything else:

1. **The current, partial ISO week is plotted as if complete.** Every weekly bar or
   line ends with a drop, and the week-on-week growth chart is negative for every
   discipline on any day but Sunday. Exclude the current week from weekly series, or
   mark it provisional the way `posting_volume_line` already does.
2. **`first_seen` is still the time axis for several charts.** The scraper went live
   on 26 May and backfilled 1,836 adverts in one week, so anything monthly by
   `first_seen` shows a June cliff that is the scraper, not the market. Use
   `date_posted` everywhere (it is 100% filled).
3. **The 30-day lookback is applied to trend charts.** A trend chart with five points
   cannot show a trend. Trend charts should draw the full history and ignore the
   lookback; the lookback belongs to cross-sectional charts only.

## Wrong or misleading: fix or remove

| Chart | Problem | Recommendation |
|---|---|---|
| `category_growth_bar` (Roles) and the growth alerts on Overview | Compares the current partial week with the last full week, so every discipline reads as shrinking mid-week. The "Key Market Insights" panel repeats this as prose. | Compare the last two complete weeks, or two trailing 7-day windows on `date_posted`. Until then this chart and its alert are actively misleading. |
| `seasonal_heatmap`, `seasonal_bar` (Trends › Volume) | Built on `first_seen`, so June carries the backfill spike. Legacy job-type slugs appear as rows. One summer of data cannot show seasonality. | Remove both until there are 12 months of `date_posted`. A monthly-postings bar on `date_posted` can replace `seasonal_bar` if a monthly view is wanted. |
| `longevity_histogram` (Institutions › Dynamics) | Measures `last_seen − first_seen`, but the scraper stops paging at the first fully-known page, so `last_seen` is only refreshed for adverts near the top. 65% of adverts show as "visible" for 7 days or fewer. This is scraper depth, not time on market. | Remove. `application_window_hist` already measures time on market correctly from `closing_date − date_posted`. |
| `salary_inflation_line` (Trends › Pay) | Monthly average floor per discipline, eight crossing lines, the current partial month included, and advertised floors sit on national spine points so there is no movement to show. September reads as a £10k drop for two disciplines on a handful of adverts. | Remove until a full pay-award cycle is in the data. If a pay chart over time is wanted, one line, quarterly median, minimum sample, `date_posted`. |
| `salary_box_by_category` (Roles › Salaries) | "Most recent week" means the partial week: a few adverts per discipline, so ranges swing wildly. | Replace with a 90-day median-and-IQR per discipline. There is no cross-sectional salary-by-discipline chart at present, which is the one people actually want. |
| `keyword_premium_bar` (Roles › Salaries) | Minimum occurrence is 2, so the top "keywords" are `signal`, `above`, `chain`, `unit`, `ocean`, `vision`. Tokens, not roles. | Raise the floor to 15 or more and restrict to a curated role vocabulary, or drop it. The pay ladder chart already answers the real question. |
| `salary_by_region_bar` (Institutions › Geography) | International reads as the best-paid region at £49k median. Those are converted foreign salaries with 47% disclosure. | Drop International from this chart, as `intl_vs_uk_profile_bars` already does for pay. |
| Discipline breakdowns that still show legacy slugs (`seasonal_heatmap`, `salary_transparency_breakdown`, `region_category_heatmap`) | Untagged pre-June rows fall back to `academic-or-research`, `further-education`, `professional-or-managerial`. | Filter `config.LEGACY_JOB_TYPE_SLUGS` in every discipline query, as `recruitment_mix_by_discipline` does. |

## Flat because of the window: weak, not wrong

These are five-point lines at the default lookback. None is incorrect, but none says
anything, and a reader learns nothing from a flat line with a y-axis to 100.

- `category_share_area`, `salary_percentile_bands`, `salary_transparency_line`,
  `permanent_ratio_line`, `recruitment_window_line`, `market_concentration_line`,
  `new_vs_repeat_bar`.

Two options. Draw them over the full 14 weeks regardless of lookback, and accept
that most will still be flat because the market is stable over a summer. Or replace
the flat ones with stat tiles that state the level, which is the actual finding:
median application window 21 days, 15% of adverts hide pay, 38% permanent, HHI
around 200. A stat tile with a sparkline carries the same information in a tenth
of the space, and the trend chart can come back when it has a year behind it.

## Sound: keep

- **Volume:** `daily_jobs_line`, `posting_volume_line` (the model for how to handle
  the provisional tail), `weekday_cadence_bar`.
- **Timing:** `application_window_hist`, `application_window_by_discipline_bar`,
  `upcoming_deadlines_bar`, `deadline_pressure_bar`.
- **Contracts:** `contract_type_bar`, `hours_bar` (both need the partial-week fix),
  `precarity_mix_bar`, `precarity_matrix_heatmap`.
- **Pay:** `salary_distribution_hist`, `salary_by_contract_bar`,
  `seniority_salary_ladder_bar`, `salary_transparency_breakdown`.
- **Institutions:** `top_institutions_bar`, `institution_salary_scatter`,
  `recruiter_concentration_curve`, `most_reposted_bar`.
- **Geography:** `region_bar`, `region_choropleth` (one of these is enough),
  `top_locations_bar`, `region_category_heatmap`, `intl_vs_uk_profile_bars`,
  `international_destinations_bar`.
- **Roles:** `seniority_breakdown_bar`, with a caveat below. `title_frequency_bar`
  is harmless but says little beyond "lecturer".

`seniority_breakdown_bar`: "Other / Unclassified" is the second-largest bucket at
1,324 adverts. The classifier needs another pass (professional services titles,
"fellow" without "research", clinical grades) before the breakdown is quotable.

## What the new data supports that the dashboard does not yet show

- **Sub-disciplines.** 89 sub-discipline tags were captured as a by-product of the
  attribution fix and nothing reads them. A drill-down from discipline to
  sub-discipline (counts, fixed-term share, pay) is the most valuable addition
  available and costs one query.
- **Non-academic disciplines.** 20 professional-services areas (administrative,
  student services, senior management, library) are tagged and unused. The 219
  adverts with no academic discipline belong here rather than in discipline charts.
- **The attribution story itself.** The dumbbell from `scripts/attribution_chart.py`
  belongs on the Data tab: it is the honest explanation of why discipline counts
  sum to more than the advert total.
- **Institution × discipline profiles.** With 55 institutions at 30+ adverts, a
  small-multiples or heatmap view of each large recruiter's discipline mix and
  fixed-term share is now supportable. The drill-down exists but shows volume only.
- **Data health.** `trends.scraper_health` exists; a small panel with last scrape,
  adverts per day, enrichment and discipline-tag coverage would replace the
  scrape-error list with something a reader can interpret.

## Suggested shape after the cull

About 25 charts. Overview: volume line, weekday cadence, four stat tiles (median
window, hidden-pay share, permanent share, adverts this week vs last complete
week). Trends: full-history weekly volume and contract split only. Pay: histogram,
ladder, by contract, by discipline (new), transparency by group. Contracts and
timing as now. Institutions and geography as now minus the region duplicate and
the longevity histogram. Roles: seniority (after the classifier pass), precarity
mix, sub-discipline drill-down (new). Data: attribution dumbbell, health panel, raw
table.

Nothing here needs new data. All of it is query and layout work against what the
scraper already holds.
