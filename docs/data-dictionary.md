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
| `first_seen` | TEXT (ISO-8601 UTC) | scraper | 100% | When this job_id was first observed. Drives all "new jobs over time" charts. |
| `last_seen` | TEXT (ISO-8601 UTC) | scraper | 100% | Updated every scrape the job still appears. `last_seen - first_seen` ⇒ listing longevity. |

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

| Tab | Chart | Function | Needs |
|-----|-------|----------|-------|
| Overview | New postings per day (+7-day avg) | `daily_jobs_line` | first_seen |
| Overview | Weekly postings by category | `category_weekly_bar` | first_seen, category |
| Trends | Category share over time | `category_share_area` | first_seen, category |
| Trends | Salary percentile bands (p25/50/75) | `salary_percentile_bands` | salary_min, first_seen |
| Trends | Seasonality heatmap | `seasonal_heatmap` | first_seen, category |
| Trends | Monthly postings by category | `seasonal_bar` | first_seen, category |
| Trends | Avg salary floor by category over time | `salary_inflation_line` | salary_min, first_seen |
| Trends | Salary transparency (% hiding pay) | `salary_transparency_line` | salary_min, first_seen |
| Trends | Permanent vs fixed-term per week | `contract_type_bar` | contract_type (enriched) |
| Trends | Precarity by discipline × recruitment mix | `precarity_mix_bar` | contract_type, title, date_posted, job_disciplines |
| Trends | Permanent contract share % | `permanent_ratio_line` | contract_type (enriched) |
| Trends | Full- vs part-time per week | `hours_bar` | hours (enriched) |
| Trends | Application window length (over time) | `recruitment_window_line` | closing_date, date_posted (enriched) |
| Trends | Time on market (window distribution) | `application_window_hist` | closing_date, date_posted (enriched) |
| Trends | Upcoming deadlines by week | `upcoming_deadlines_bar` | closing_date (enriched) |
| Roles | Median salary: permanent vs fixed-term | `salary_by_contract_bar` | contract_type (enriched), salary_min |
| Institutions | Median salary by region | `salary_by_region_bar` | region (enriched), salary_min |
| Institutions | UK postings choropleth map | `region_choropleth` | region (enriched) + bundled uk_nations.geojson |
| Institutions | Region × category concentration | `region_category_heatmap` | region, category (enriched) |
| Institutions | Jobs by UK nation / International | `region_bar` | region (enriched) |
| Institutions | Top hiring locations | `top_locations_bar` | location (enriched) |
| Roles | Postings by seniority band | `seniority_breakdown_bar` | title, salary_min |
| Roles | Salary floor distribution | `salary_distribution_hist` | salary_min |
| Roles | Most frequent title words | `title_frequency_bar` | title |
| Roles | Category growth (WoW %) | `category_growth_bar` | first_seen, category |
| Roles | Salary range by category | `salary_box_by_category` | salary_min/max, category |
| Roles | Keyword salary premium | `keyword_premium_bar` | title, salary_min, category |
| Institutions | Top recruiting institutions | `top_institutions_bar` | institution, first_seen |
| Institutions | Salary vs volume scatter | `institution_salary_scatter` | institution, salary_min |
| Institutions | Recruitment concentration (HHI) | `market_concentration_line` | institution, first_seen |
| Institutions | New vs returning recruiters | `new_vs_repeat_bar` | institution, first_seen |
| Institutions | Listing longevity histogram | `longevity_histogram` | first_seen, last_seen |

## Re-measuring fill rates

```python
import sqlite3
c = sqlite3.connect("data/jobs.db")
n = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
for col in ["department","salary_min","closing_date","contract_type","hours"]:
    f = c.execute(f"SELECT COUNT({col}) FROM jobs").fetchone()[0]
    print(f"{col:14s} {f:4d}/{n}  ({100*f//n}%)")
```
