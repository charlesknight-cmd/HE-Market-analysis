# Architecture

## Data flow

```
jobs.ac.uk /search/<category> (6 categories)
        │   scraper/fetcher.py  — parallel, paginated, incremental download (ThreadPoolExecutor)
        ▼
   search-result HTML pages
        │   scraper/parser.py   — parse_listing_html / parse_listing_card / parse_salary
        ▼
   clean job dicts
        │   db/queries.py       — bulk_upsert (dedupe by job_id; update last_seen)
        ▼
   SQLite  data/jobs.db  (WAL mode)   ◄── db/schema.py (tables, migrations, indexes)
        │
        ├── analysis/  (read-only queries: trends, institutions, alerts) ──► analysis/report.py (CLI text)
        │
        └── dashboard/app.py  (Streamlit, @st.cache_data ttl=300) ──► dashboard/charts.py (Plotly figures)
```

A scrape run is orchestrated by `scraper/run.py`:

- `run_once()` — fetch all categories, parse, `bulk_upsert`, and `log_run` into `scrape_runs`.
- `run_daemon()` — run once, then `schedule` a daily repeat at `config.SCHEDULE_TIME`.
  (In production a **cron job** is used instead of daemon mode — see below.)

## Components

| Layer | Module | Responsibility |
|-------|--------|----------------|
| Config | `config.py` | Search URLs, pagination/politeness, category labels, schedule time, alert thresholds, HTTP headers, DB path |
| Scrape | `scraper/fetcher.py` | Download all categories in parallel; paginate per category, stopping early on already-seen jobs |
| Scrape | `scraper/parser.py` | Turn search-result cards into clean job dicts; normalise salary/dates; infer year on year-less listing dates |
| Scrape | `scraper/run.py` | CLI entry point; one-shot and daemon orchestration |
| Persist | `db/schema.py` | Connection (WAL), schema creation, idempotent `_migrate`, index creation |
| Persist | `db/queries.py` | `upsert_job`, `bulk_upsert`, `existing_job_ids`, `log_run`, `last_scrape_time`, `get_all_jobs`, `get_jobs_since` |
| Analyse | `analysis/trends.py` | Time-series & statistical queries (volume, shares, salary percentiles, HHI, seniority, transparency, …) |
| Analyse | `analysis/institutions.py` | Institution-level queries (top recruiters, spikes, salary, new-vs-repeat) |
| Analyse | `analysis/alerts.py` | "Key market insights" — surges / elevated activity / trends, severity-sorted |
| Analyse | `analysis/report.py` | Plain-text CLI report |
| Present | `dashboard/app.py` | Page config, tabs, header filter popover, cached loaders, layout |
| Present | `dashboard/charts.py` | Plotly figure builders + shared `_style_fig` theme/palette |

## Database

Two tables (see [data-dictionary.md](data-dictionary.md) for columns):

- **`jobs`** — one row per unique `job_id`; `first_seen` / `last_seen` track when a
  listing appears and was last observed in the feed.
- **`scrape_runs`** — one row per feed per scrape; records counts and status for
  operational visibility (`last_scrape_time()` reads from here).

Schema changes are additive: new columns go in `db/schema.py::_MIGRATIONS` and are
applied idempotently by `_migrate()` (safe to re-run). `init_db()` is called both by
the scraper and at dashboard startup (`@st.cache_resource`), so migrations apply
on either entry point.

### Key DB conventions

- **WAL mode** (`PRAGMA journal_mode=WAL`) so the dashboard can read while a scrape writes.
- Timestamps are ISO-8601 UTC. Trend queries normalise them with the `_CLEAN_TS`
  SQL helper (`substr(replace(first_seen,'T',' '),1,19)`) so `strftime` works across
  both `T`-separated and space-separated values.
- Indexes on `institution`, `category`, `first_seen`, `last_seen`, `contract_type`, `hours`.

## Caching

Dashboard loaders are wrapped in `@st.cache_data(ttl=300)` (5 minutes), so charts
don't re-query SQLite on every interaction. `init_db()` uses `@st.cache_resource`
to run once per worker process rather than per rerun.

## Deployment topology

```
Internet ──► nginx (TLS, jobs.charlesknight.co.uk) ──► Streamlit :8501 (he-market-dashboard.service)
                                                              │
cron 07:00 UTC ──► python -m scraper.run ──► data/jobs.db ◄───┘  (shared SQLite file, WAL)
```

- **Server:** Hetzner, `65.109.230.120`, code at `/opt/he-market-analysis`, venv at `venv/`.
- **Dashboard:** `deploy/he-market-dashboard.service` (systemd, auto-restart, enabled at boot).
- **Reverse proxy / TLS:** `deploy/nginx.conf`.
- **Scrape schedule:** cron, not daemon — `0 7 * * * cd /opt/he-market-analysis && venv/bin/python -m scraper.run >> /var/log/he-scraper.log 2>&1`.
- **Bootstrap:** `deploy/setup.sh`.

The dashboard and scraper share the one SQLite file; WAL mode keeps concurrent
read (dashboard) and write (cron scrape) safe.
