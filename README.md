# HE Market Analysis

A tool that tracks the UK Higher Education job market. It scrapes job listings
from [jobs.ac.uk](https://www.jobs.ac.uk) RSS feeds, stores them in SQLite, runs
trend analysis, and presents everything through a Streamlit dashboard.

**Live dashboard:** https://jobs.charlesknight.co.uk

## What it does

- **Scrapes** six jobs.ac.uk RSS feeds (one per job category) daily.
- **Parses** institution, department, and salary from each listing.
- **Stores** jobs in a local SQLite database (`data/jobs.db`, WAL mode), de-duplicated by job ID.
- **Analyses** trends: posting volume, category shares, salary distributions and
  percentiles, seniority bands, institution concentration (HHI), recruiter churn,
  salary transparency, and more.
- **Surfaces** it all in a 5-tab Streamlit dashboard (Overview, Trends, Roles,
  Institutions, Data) plus a plain-text CLI report.

## Stack

Python · SQLite · [feedparser](https://feedparser.readthedocs.io) + requests
(scraping) · [Streamlit](https://streamlit.io) + [Plotly](https://plotly.com/python/)
(dashboard) · `schedule` (optional daemon mode) · pytest (tests).

## Project layout

```
config.py            Feed URLs, category labels, schedule time, alert thresholds, HTTP headers
scraper/             RSS fetching and parsing
  fetcher.py           Parallel RSS download (ThreadPoolExecutor)
  parser.py            Extract institution/department/salary; normalise fields
  run.py               CLI entry point (one-shot or --daemon)
db/                  Persistence
  schema.py            Schema, WAL, idempotent migrations, indexes
  queries.py           upsert / bulk_upsert / get_all_jobs / get_jobs_since / log_run
analysis/            Read-only analytics over the DB
  trends.py            Time-series + statistical queries (the bulk of the analytics)
  institutions.py      Institution-level queries (top recruiters, spikes, churn)
  alerts.py            "Key market insights" (surges, elevated activity, trends)
  report.py            CLI text report (python -m analysis.report)
dashboard/           Streamlit UI
  app.py               Page layout, tabs, filters, cached loaders
  charts.py            Reusable Plotly figure builders + shared styling
scripts/             One-off maintenance scripts (e.g. reparse.py salary backfill)
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

## Data source & its limitations

Jobs come from the jobs.ac.uk RSS feeds listed in `config.RSS_FEEDS`. **The RSS
feed is thin** — each entry only carries institution, department, and salary.
It does **not** include closing date, contract type, working hours, or location.

As a result those columns are currently unpopulated and a few charts are paused.
Recovering them requires fetching each job's detail HTML page — see
[docs/detail-page-enrichment.md](docs/detail-page-enrichment.md) for the plan.
Field-by-field fill rates and caveats are documented in
[docs/data-dictionary.md](docs/data-dictionary.md).

## Deployment

Production runs on a Hetzner server, reverse-proxied by nginx with TLS, at
https://jobs.charlesknight.co.uk.

- **Dashboard:** `he-market-dashboard.service` (systemd) runs `streamlit run dashboard/app.py`.
- **Scrape:** a cron job runs `python -m scraper.run` daily at 07:00 UTC.
- **Code path:** `/opt/he-market-analysis`.

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
