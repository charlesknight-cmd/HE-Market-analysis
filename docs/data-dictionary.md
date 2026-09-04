# Data Dictionary

Fill rates below reflect the search-listing source adopted **2026-06-09** (the
listing-sourced columns are measured from a fresh page of results; legacy rows
predating the migration may differ). They will drift; re-measure with the snippet
at the bottom.

## Table: `jobs`

One row per unique listing, keyed by `job_id`.

| Column | Type | Source | Fill | Notes |
|--------|------|--------|------|-------|
| `id` | INTEGER PK | auto | 100% | Surrogate autoincrement key. |
| `job_id` | TEXT UNIQUE | URL | 100% | Reference code parsed from the jobs.ac.uk URL (e.g. `DRR304`). Dedupe key. |
| `title` | TEXT | listing (card title link) | 100% | Raw job title. Source for keyword & seniority analysis. |
| `institution` | TEXT | listing (`.j-search-result__employer`) | 100% | Employer name. May be an overseas institution. |
| `department` | TEXT | listing (`.j-search-result__department`) | ~90% | Faculty/department; absent when the card has no department line. |
| `salary_raw` | TEXT | listing (`Salary:` line) | ~88% | Verbatim salary string, e.g. `£41,519 to £46,618 per annum`. "Not Specified" ⇒ NULL. |
| `salary_min` | REAL | listing parse, gap-filled from JSON-LD `baseSalary` | ~88% | Lower £ bound. Hourly/sub-£10k excluded. Enrichment fills gaps (GBP annual only) but never overwrites a listing value. |
| `salary_max` | REAL | listing parse, gap-filled from JSON-LD `baseSalary` | ~88% | Upper £ bound; equals `salary_min` for single-value salaries. |
| `closing_date` | TEXT (YYYY-MM-DD) | listing (`Closes`/`Expires`), year inferred | ~100% | In the listing card; year inferred (closing dates are in the future). Enrichment fills the rare gap from JSON-LD `validThrough`. |
| `contract_type` | TEXT | detail-page JSON-LD (`employmentType`) | enriched | `permanent` / `fixed-term`. Not in the listing — enrichment only. |
| `hours` | TEXT | detail-page JSON-LD (`employmentType`) | enriched | `full-time` / `part-time` / `flexible`. Not in the listing — enrichment only. |
| `location` | TEXT | listing (`Location:` line) | ~100% | Town/city, e.g. London, Cambridge. Now in the listing card. |
| `region` | TEXT | detail-page JSON-LD (`addressRegion`/country) | enriched | UK nation (England/Scotland/Wales/Northern Ireland), `International`, or `UK (unspecified)`. The listing gives only a town, so region is still derived by enrichment. |
| `date_posted` | TEXT (YYYY-MM-DD) | listing (`Date Placed:`), year inferred | ~100% | Advertised posting date, from the card. Drives the recruitment-window calc (`closing_date − date_posted`). Enrichment confirms it from JSON-LD `datePosted`. |
| `enriched_at` | TEXT (ISO-8601 UTC) | enrichment | enriched | When the job was enriched. NULL ⇒ not yet processed (will be picked up next run). |
| `disciplines_at` | TEXT (ISO-8601 UTC) | enrichment / `scripts.backfill_disciplines` | enriched | When the detail page's Subject Area(s) were captured into `job_disciplines`. NULL ⇒ pending backfill. |
| `category` | TEXT | discipline facet slug | 100% | **The discipline facet the job was first scraped under — not its full set of disciplines.** A job tagged with several disciplines (common: ~2 in 3 STEM jobs) keeps only the first-scanned one here. Use `job_disciplines` / the `jobs_by_discipline` view for attribution; treat this column as provenance. Rows from before the 2026-06-09 taxonomy change hold a legacy job-type slug (`academic-or-research`, …). |
| `url` | TEXT | listing (card title link) | 100% | Canonical listing URL; also the detail page fetched for enrichment. |
| `first_seen` | TEXT (ISO-8601 UTC) | scraper | 100% | When this job_id was first observed. Provenance only: no chart uses it as a time axis (the 26 May 2026 backfill put 1,836 adverts into one week). |
| `last_seen` | TEXT (ISO-8601 UTC) | scraper | 100% | Updated every scrape the job still appears near the top of its facet. NOT a lifetime measure: the scraper stops paging at the first fully-known page, so older adverts stop being refreshed. |

> Most fields now come straight from the search-results card (jobs.ac.uk retired
> its RSS feeds ~June 2026). `closing_date`, `location`, and `date_posted` — which
> the old feed lacked entirely — are parsed directly from the listing, so they are
> populated at insert time rather than waiting on enrichment. **"enriched" fill**
> still applies to `contract_type`, `hours`, and `region`, which aren't in the
> listing and are recovered from the schema.org `JobPosting` JSON-LD on each detail
> page — see [detail-page-enrichment.md](detail-page-enrichment.md). The daily scrape
> enriches up to 200 new jobs; `python -m scripts.enrich_backfill` clears any backlog.

## Table: `job_disciplines`

One row per (job, subject-area tag). jobs.ac.uk tags each job with any number of
**academic disciplines** (the 21 facets we scrape), their **sub-disciplines**
(e.g. `artificial-intelligence` under `computer-sciences`) and **non-academic
disciplines** (e.g. `student-services`). The detail page lists them all in its
"Subject Area(s)" sidebar; every listing scan also contributes the facet it ran
under. This table — not `jobs.category` — is the source of truth for
discipline attribution.

| Column | Type | Notes |
|--------|------|-------|
| `job_id` | TEXT | FK to `jobs.job_id`. |
| `facet` | TEXT | `academic` / `sub` / `non-academic`. Primary key with `job_id` + `slug`. |
| `slug` | TEXT | Facet value, e.g. `computer-sciences`, `artificial-intelligence`. |
| `name` | TEXT | Display name from the detail page. NULL when recovered from an expired-job redirect. |
| `parent_slug` | TEXT | For `sub` rows: the academic discipline it belongs to (NULL if unknowable from a redirect with several academic facets). |
| `source` | TEXT | `listing` (facet scan) < `redirect` (expired-job redirect URL) < `detail` (Subject Area(s) block). Upserts only ever raise authority. |
| `position` | INTEGER | Order on the detail page within the facet (0 = first-listed). NULL for listing-sourced rows. |
| `first_seen` / `last_seen` | TEXT (ISO-8601 UTC) | When the tag was first/last observed. |

**Coverage.** New jobs get their tags during the daily enrichment. Historic rows
are filled by `python -m scripts.backfill_disciplines` (newest-closing first):
jobs.ac.uk serves a full detail page for ~45 days after closing, then a
redirect to `/search/?academicDisciplineFacet[0]=…&expired-job-redirect=true`
that still names the facets, so every job is recoverable — older ones just
lack display names and sub-discipline parents. `--status` prints coverage.

### Views

| View | Rows | Use for |
|------|------|---------|
| `jobs_by_discipline` | one per job × academic discipline (`category` = that discipline; `position` = page order). Jobs with no `job_disciplines` row yet fall back to `jobs.category`, so it is never emptier than `jobs`. | Anything grouped by discipline: counts, shares, salary by discipline, casualisation, application windows. A multi-discipline job counts under each. |
| `jobs_primary_discipline` | exactly one per job (`category` = first-listed academic discipline, else `jobs.category`). | Per-job distributions that must not double count but still want a discipline label (salary histogram, keyword-premium baselines). |

Both views are (re)created by `init_db()` whenever their SQL changes, and pass
every `jobs` column through, so a later column migration is picked up automatically.

## Table: `scrape_runs`

One row per feed per scrape — operational audit log.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | auto |
| `run_at` | TEXT (ISO-8601 UTC) | When the run happened. `last_scrape_time()` returns the max. |
| `category` | TEXT | Which feed this row is for. |
| `jobs_found` | INTEGER | Entries seen in the feed this run. |
| `jobs_new` | INTEGER | Newly inserted rows. |
| `jobs_updated` | INTEGER | Existing rows whose `last_seen` was bumped. |
| `status` | TEXT | `ok` or `error`. |
| `error` | TEXT | Error detail when `status = error`. |

## Category slugs (subject disciplines)

Since 2026-06-09 `category` holds one of jobs.ac.uk's 21 subject-discipline slugs
— e.g. `biological-sciences`, `computer-sciences`, `engineering-and-technology`,
`health-and-medical`, `law`, `psychology`, `social-sciences-and-social-care`. The
full slug→name map is `config.DISCIPLINES`. The largest disciplines are Health &
Medical, Computer Sciences, and Engineering & Technology (each ~330–360 live
postings); the long tail (Agriculture, Sport & Leisure, …) runs to a few dozen.

Rows scraped before that date carry a **legacy job-type slug** (`academic-or-research`,
`professional-or-managerial`, `further-education`, …) from the retired feed
taxonomy in `category`; once the discipline backfill has run they carry proper
discipline tags in `job_disciplines` and appear under those in `jobs_by_discipline`.

**Multi-discipline jobs.** A job can be tagged with several of the 21
disciplines, so discipline counts in the dashboard sum to more than the number
of jobs, and "share" charts are shares of discipline *tags*. Before this was
tracked (September 2026) each job was attributed to whichever facet the scraper
happened to scan first — alphabetical order, which inflated `agriculture…` and
`biological-sciences` and starved later ones. Any discipline-level figure in
`jobs.category` alone is subject to that bias; use the view.

## Chart catalogue

Built in `dashboard/charts.py`, laid out across tabs in `dashboard/app.py`.
Since the September 2026 review every windowed chart keys off `date_posted`;
weekly series show every COMPLETE ISO week and ignore the lookback control;
discipline breakdowns read `jobs_by_discipline` (a multi-discipline advert
counts under each) and skip `config.LEGACY_JOB_TYPE_SLUGS`; fixed-term shares
exclude PhD studentships (`trends.is_studentship`).

| Tab | Chart | Function | Needs |
|-----|-------|----------|-------|
| Overview | Headline figures (adverts, last complete week vs previous, median days to apply, hidden-pay share, permanent share, institutions) | `st.metric` via `trends.headline_stats` | date_posted, closing_date, salary_min, contract_type, title |
| Overview | Postings per day (+7-day avg, provisional tail) | `posting_volume_line` | date_posted |
| Overview | Weekly postings by discipline (complete weeks) | `category_weekly_bar` | date_posted, job_disciplines |
| Overview | Weekday posting cadence | `weekday_cadence_bar` | date_posted |
| Trends | Discipline share of weekly tags | `category_share_area` | date_posted, job_disciplines |
| Trends | Permanent vs fixed-term per week | `contract_type_bar` | contract_type, date_posted |
| Trends | Full- vs part-time per week | `hours_bar` | hours, date_posted |
| Pay | Salary floor distribution | `salary_distribution_hist` | salary_min |
| Pay | Median salary: permanent vs fixed-term | `salary_by_contract_bar` | contract_type, salary_min |
| Pay | Median full-time salary floor by discipline (+IQR) | `salary_by_discipline_bar` | salary_min, hours, job_disciplines |
| Pay | Academic pay ladder by seniority (+IQR) | `seniority_salary_ladder_bar` | title, salary_min, hours |
| Pay | Salary-transparency gap by discipline and region | `salary_transparency_breakdown` | salary_min, region, job_disciplines |
| Pay | Median salary floor by UK nation | `salary_by_region_bar` | region, salary_min |
| Contracts & Timing | Precarity by discipline × recruitment mix | `precarity_mix_bar` | contract_type, title, job_disciplines |
| Contracts & Timing | Contract × hours precarity matrix | `precarity_matrix_heatmap` | contract_type, hours |
| Contracts & Timing | Application window distribution | `application_window_hist` | closing_date, date_posted |
| Contracts & Timing | Days-to-apply by discipline (+IQR) | `application_window_by_discipline_bar` | closing_date, date_posted, job_disciplines |
| Contracts & Timing | Upcoming deadlines by week | `upcoming_deadlines_bar` | closing_date |
| Contracts & Timing | Deadline-pressure pipeline | `deadline_pressure_bar` | closing_date |
| Roles | Postings by seniority band | `seniority_breakdown_bar` | title, salary_min |
| Roles | Sub-discipline drill-down (count, fixed-term share, median pay) | `tag_breakdown_bar` via `trends.subdiscipline_breakdown` | job_disciplines (facet `sub`) |
| Roles | Professional-services areas | `tag_breakdown_bar` via `trends.nonacademic_breakdown` | job_disciplines (facet `non-academic`) |
| Institutions | Top recruiting institutions | `top_institutions_bar` | institution, date_posted |
| Institutions | Spike watch table | `institutions.spike_candidates` | institution, job_disciplines |
| Institutions | Institution drill-down (complete weeks + discipline table) | `px.bar` via `institution_weekly_trend`, `institution_category_breakdown` | institution, date_posted, job_disciplines |
| Institutions | Recruiter concentration (Lorenz, Gini) | `recruiter_concentration_curve` | institution, date_posted |
| Institutions | Pay floor vs hiring volume | `institution_salary_scatter` | institution, salary_min |
| Institutions | Most re-advertised roles | `most_reposted_bar` | title, institution, date_posted |
| Institutions | Jobs by UK nation / International | `region_bar` | region |
| Institutions | Top hiring locations | `top_locations_bar` | location |
| Institutions | Region × discipline concentration | `region_category_heatmap` | region, job_disciplines |
| Institutions | International vs UK structural profile | `intl_vs_uk_profile_bars` | region, contract_type, hours, salary_min |
| Institutions | International destinations by city | `international_destinations_bar` | region, location |
| Data | Scraper health and fill-rate metrics | `st.metric` via `trends.scraper_health`, `trends.data_coverage` | scrape_runs, enrichment columns |
| Data | Attribution dumbbell (counted once vs every subject) | `attribution_dumbbell` | job_disciplines |
| Data | Raw table + CSV export | `st.dataframe` | all columns |

Removed in September 2026 (see `docs/dashboard-review-2026-09.md`): the
`first_seen`-based daily line, seasonality heatmap and monthly bar, the
salary-inflation and percentile-band lines, the weekly transparency, permanent-
share, application-window, HHI and new-vs-returning lines (flat five-point
series replaced by headline figures), the `last_seen`-based longevity histogram
(a scraper-depth artefact), the week-on-week growth bar (its query still feeds
the insights, now on complete weeks), the most-recent-week salary range, the
keyword-premium bar, the title-word bar and the UK choropleth.

## Re-measuring fill rates

```python
import sqlite3
c = sqlite3.connect("data/jobs.db")
n = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
for col in ["department","salary_min","closing_date","contract_type","hours"]:
    f = c.execute(f"SELECT COUNT({col}) FROM jobs").fetchone()[0]
    print(f"{col:14s} {f:4d}/{n}  ({100*f//n}%)")
```
