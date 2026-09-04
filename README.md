# HE Market Analysis

A tool that tracks the UK Higher Education job market. It scrapes job listings
from [jobs.ac.uk](https://www.jobs.ac.uk), stores them in SQLite, runs
trend analysis, and presents everything through a Streamlit dashboard.

**Live dashboard:** https://jobs.charlesknight.co.uk

## What it does

- **Scrapes** jobs.ac.uk search-results listings across its 21 subject
  disciplines (one filtered search per discipline) daily.
- **Parses** institution, department, salary, location, date placed, and closing
  date from each listing.
- **Stores** jobs in a local SQLite database (`data/jobs.db`, WAL mode), de-duplicated by job ID.
- **Analyses** trends: posting volume, category shares, salary distributions and
  percentiles, seniority bands, institution concentration (HHI), recruiter churn,
  salary transparency, and more.
- **Surfaces** it all in a 5-tab Streamlit dashboard (Overview, Trends, Roles,
  Institutions, Data) plus a plain-text CLI report.

## Stack

Python · SQLite · [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) + requests
(scraping) · [Streamlit](https://streamlit.io) + [Plotly](https://plotly.com/python/)
(dashboard) · `schedule` (optional daemon mode) · pytest (tests).

## Project layout

```
config.py            Search URLs, pagination/politeness, category labels, schedule, alert thresholds, HTTP headers
scraper/             Listing fetching and parsing
  fetcher.py           Parallel per-category download (ThreadPoolExecutor), paginated, incremental
  parser.py            Parse search-result cards into clean job dicts; normalise fields
  run.py               CLI entry point (one-shot or --daemon)
db/                  Persistence
  schema.py            Schema, WAL, idempotent migrations, indexes
  queries.py           upsert / bulk_upsert / get_all_jobs / get_jobs_since / log_run / job_disciplines helpers
analysis/            Read-only analytics over the DB
  trends.py            Time-series + statistical queries (the bulk of the analytics)
  institutions.py      Institution-level queries (top recruiters, spikes, churn)
  alerts.py            "Key market insights" (surges, elevated activity, trends)
  report.py            CLI text report (python -m analysis.report)
dashboard/           Streamlit UI
  app.py               Page layout (Overview · Trends · Pay · Contracts & Timing · Roles · Institutions · Data), filters, cached loaders
  charts.py            Reusable Plotly figure builders + shared styling
scripts/             One-off maintenance and reporting scripts (reparse.py salary backfill, backfill_disciplines.py, enrich_backfill.py, backup_db.py, casualisation_chart.py and attribution_chart.py PNGs for sharing)
tests/               pytest suite (parser tests)
deploy/              systemd unit, nginx config, setup script
docs/                Design notes & reference (architecture, data dictionary, enrichment scope)
```

## Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows;  source venv/bin/activate on Linux/macOS
pip install -r requirements.txt
```

The database is created automatically on first run (and on dashboard startup).

## Usage

```bash
# Scrape once (fetch all feeds, upsert into the DB)
python -m scraper.run

# Scrape once, then repeat daily at config.SCHEDULE_TIME (07:00)
python -m scraper.run --daemon

# Print a text trend report for the last 30 days
python -m analysis.report

# Launch the dashboard locally at http://localhost:8501
streamlit run dashboard/app.py
```

## Data source

Jobs come from the jobs.ac.uk search-results pages, scraped one **subject
discipline** at a time (the 21 disciplines in `config.DISCIPLINES`). Around June
2026 jobs.ac.uk **retired its RSS feeds** (the old `?format=rss` URLs now return
HTTP 500 or HTML) **and dropped its six job-type category routes** (which all now
return the same unfiltered list). Its live taxonomy is subject disciplines,
selected via the search facet `academicDisciplineFacet[]=<slug>` — so the scraper
filters on that and stores the discipline in the `category` column. The
server-rendered cards carry more than the old feed ever did: title, institution,
department, salary, **location**, **date placed**, and **closing date**. Each
discipline is paginated (`?academicDisciplineFacet[]=<slug>&pageSize=25&startIndex=N`,
date-sorted), and the daily run pages from newest until it reaches jobs already in
the DB (`MAX_PAGES_PER_CATEGORY` bounds the first catch-up; `scraper.run --full`
forces a full re-page). The facet is in every request URL, so requests are
stateless — important, because jobs.ac.uk otherwise tracks the active search per
client. Contract type, working hours, and UK region/nation are still recovered
from each job's detail-page JSON-LD by the enrichment step — see
[docs/detail-page-enrichment.md](docs/detail-page-enrichment.md). Field-by-field
fill rates are in [docs/data-dictionary.md](docs/data-dictionary.md).

## Deployment

Production runs on a Hetzner server, reverse-proxied by nginx with TLS, at
https://jobs.charlesknight.co.uk.

- **Dashboard:** `he-market-dashboard.service` (systemd) runs `streamlit run dashboard/app.py`.
- **Scrape:** a cron job runs `python -m scraper.run` daily at 07:00 UTC.
- **Code path:** `/opt/he-market-analysis`.
- **Discipline tags:** new jobs get their full set of subject disciplines during
  the daily enrichment. After deploying a schema change, or to fill historic
  rows, run `python -m scripts.backfill_disciplines` (about one request per
  second; `--status` shows coverage without fetching).

Deploy a change:

```bash
ssh root@65.109.230.120 "cd /opt/he-market-analysis && git pull && systemctl restart he-market-dashboard"
```

Verify:

```bash
ssh root@65.109.230.120 "systemctl status he-market-dashboard --no-pager"
```

The dashboard can be password-gated by setting `password` in
`.streamlit/secrets.toml` (see `secrets.toml.example`).

See `deploy/` for the systemd unit, nginx config, and setup script, and
[docs/architecture.md](docs/architecture.md) for the full topology.

## Development

This repo ships a git pre-commit hook (in `.githooks/`) that blocks a commit
unless `CHANGELOG.md` is updated, keeping the changelog current. Enable it once
per clone:

```bash
git config core.hooksPath .githooks
```

Add your entry under the `[Unreleased]` section of `CHANGELOG.md`. If a change
genuinely doesn't warrant an entry, bypass with `SKIP_CHANGELOG=1 git commit ...`.

## Tests

```bash
pytest
```

## License

See [LICENSE](LICENSE).
