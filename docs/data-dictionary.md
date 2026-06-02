# Data Dictionary

Fill rates below are a snapshot from the production DB on **2026-06-02 (227 jobs)**.
They will drift; re-measure with the snippet at the bottom.

## Table: `jobs`

One row per unique listing, keyed by `job_id`.

| Column | Type | Source | Fill | Notes |
|--------|------|--------|------|-------|
| `id` | INTEGER PK | auto | 100% | Surrogate autoincrement key. |
| `job_id` | TEXT UNIQUE | URL | 100% | Reference code parsed from the jobs.ac.uk URL (e.g. `DRR304`). Dedupe key. |
| `title` | TEXT | RSS title | 100% | Raw job title. Source for keyword & seniority analysis. |
| `institution` | TEXT | RSS desc (line 1, before ` - `) | 100% | Employer name. May be an overseas institution. |
| `department` | TEXT | RSS desc (line 1, after ` - `) | ~75% | Faculty/department; absent when the listing has no ` - ` segment. |
| `salary_raw` | TEXT | RSS desc (`Salary:` line) | ~83% | Verbatim salary string, e.g. `£41,519 to £46,618 per annum`. "Not specified" ⇒ NULL after parsing. |
| `salary_min` | REAL | parsed | ~83% | Lower £ bound. Hourly rates and values < £10,000 are excluded (see `parse_salary`). |
| `salary_max` | REAL | parsed | ~83% | Upper £ bound; equals `salary_min` for single-value salaries. |
| `closing_date` | TEXT (YYYY-MM-DD) | detail-page JSON-LD (`validThrough`) | enriched | Populated by enrichment, not RSS. NULL until a job is enriched. |
| `contract_type` | TEXT | detail-page JSON-LD (`employmentType`) | enriched | `permanent` / `fixed-term`. |
| `hours` | TEXT | detail-page JSON-LD (`employmentType`) | enriched | `full-time` / `part-time` / `flexible`. |
| `location` | TEXT | detail-page JSON-LD (`addressLocality`) | enriched | Town/city, e.g. London, Cambridge. |
| `region` | TEXT | detail-page JSON-LD (`addressRegion`/country) | enriched | UK nation (England/Scotland/Wales/Northern Ireland) or `International`. |
| `enriched_at` | TEXT (ISO-8601 UTC) | enrichment | enriched | When the job was enriched. NULL ⇒ not yet processed (will be picked up next run). |
| `category` | TEXT | feed slug | 100% | Which RSS feed it came from (see `config.RSS_FEEDS`). |
| `url` | TEXT | RSS link | 100% | Canonical listing URL; also the detail page fetched for enrichment. |
| `first_seen` | TEXT (ISO-8601 UTC) | scraper | 100% | When this job_id was first observed. Drives all "new jobs over time" charts. |
| `last_seen` | TEXT (ISO-8601 UTC) | scraper | 100% | Updated every scrape the job still appears. `last_seen - first_seen` ⇒ listing longevity. |

> **"enriched" fill** means the column is populated for every job that has been
> through detail-page enrichment (`enriched_at IS NOT NULL`). The RSS feed itself
> carries only institution, department, and salary; `closing_date`,
> `contract_type`, `hours`, `location`, and `region` all come from parsing the
> schema.org `JobPosting` JSON-LD on each detail page — see
> [detail-page-enrichment.md](detail-page-enrichment.md). The daily scrape enriches
> up to 200 new jobs; `python -m scripts.enrich_backfill` clears any backlog.

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

## Category slugs

`academic-or-research`, `professional-or-managerial`, `technical`, `clerical`,
`further-education`, `craft-or-manual`. Display names are in
`config.CATEGORY_LABELS`. **`technical`, `clerical`, and `craft-or-manual` feeds
are typically sparse or empty.** Current data is dominated by academic-or-research
and professional-or-managerial.

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
| Trends | Permanent contract share % | `permanent_ratio_line` | contract_type (enriched) |
| Trends | Full- vs part-time per week | `hours_bar` | hours (enriched) |
| Trends | Application window length | `recruitment_window_line` | closing_date (enriched), first_seen |
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
