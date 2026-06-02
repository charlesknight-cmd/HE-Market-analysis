# Detail-Page Enrichment — Scoping

**Status:** proposed / not yet built
**Author:** handover notes, 2026-06-02

## Why

The jobs.ac.uk RSS feed is thin. A live entry's `summary` field contains only:

```
University of Hong Kong - Faculty of Education<br />Salary: Not specified
```

That is the **entire** machine-readable payload: institution, department, salary. The feed carries **no closing date, no contract type, no working hours, and no location**.

As a result, on the current production DB (227 jobs):

| Field           | Fill rate |
|-----------------|-----------|
| institution     | 100%      |
| category        | 100%      |
| salary_min/max  | 83%       |
| department      | 75%       |
| closing_date    | **0%**    |
| contract_type   | **0%**    |
| hours           | **0%**    |
| location/region | (no column) |

Four dashboard charts were built against the empty columns and have been **paused** (removed from the UI in the meantime): recruitment-window, contract-type bar, hours bar, permanent-share line. The headline **geographic view** (an original project goal) is impossible without location data.

All of these fields *do* exist on each job's **detail HTML page** (e.g. `https://www.jobs.ac.uk/job/DRR304/...`). Enrichment = fetch that page per job and parse the structured fields.

## Goal

For each job we already store, fetch its detail page and populate:

- `closing_date` (already a column — currently always NULL)
- `contract_type` (already a column)
- `hours` (already a column)
- `location` **(new column)** — the town/city string
- `region` **(new column)** — normalised UK region / "International"

Then un-pause the 4 charts and add a UK regional map.

## Approach

1. **Schema** — add `location TEXT` and `region TEXT` via the existing `_MIGRATIONS` list in `db/schema.py` (the migration runner is already idempotent). No other schema change needed; the other three columns exist.

2. **Detail fetcher** — new `scraper/detail.py`:
   - `fetch_detail(url) -> html` using `requests` with the project's existing session/headers and a timeout.
   - `parse_detail(html) -> dict` extracting the placed fields. jobs.ac.uk detail pages render the key facts in a definition list / labelled rows ("Location:", "Closing date:", "Contract Type:", "Hours:"). Parse with `selectolax` or `BeautifulSoup` (add to `requirements.txt`) rather than regex over raw HTML.
   - Reuse the existing `_parse_closing_date` / `_parse_contract_type` / `_parse_hours` helpers in `scraper/parser.py` — they already normalise the *values*; only the *source* changes from RSS to detail HTML.

3. **Region normalisation** — a `LOCATION_TO_REGION` map (or a small lookup) turning a city/town string into one of the 12 UK regions (or "Scotland"/"Wales"/"Northern Ireland"/"International"). Start with a dict of the most common HE cities; fall back to "Unknown".

4. **Politeness / rate-limiting (important)** — this is the main risk. The RSS scrape is one request per category (6 total); enrichment is **one request per job**.
   - Only enrich jobs **missing** the fields (`WHERE closing_date IS NULL`), so steady-state is just the day's new jobs (~tens, not hundreds).
   - Sequential with a deliberate delay (e.g. 1–2 s) between requests; do **not** reuse the RSS `ThreadPoolExecutor` parallelism here.
   - Set a clear `User-Agent`, honour `robots.txt`, and cap per-run volume (e.g. 200 jobs/run) with a `log()`-style note when capped.
   - Cache by `job_id` — never re-fetch an already-enriched job.

5. **Wiring** — call enrichment as a second step in `scraper/run.py` after the RSS upsert, or as a separate cron entry staggered after 07:00 (e.g. 07:15) so the two concerns stay independent.

6. **Backfill** — a `scripts/enrich_backfill.py` (mirroring the existing `scripts/reparse.py`) to walk all historical jobs once, respecting the same rate limit. ~227 jobs × ~1.5 s ≈ a few minutes.

## Testing

- Unit-test `parse_detail` against 2–3 saved HTML fixtures (one international, one UK, one with "Not specified" salary), matching the style of `tests/test_parser.py`.
- Verify region mapping covers the current top-20 institutions' cities.

## Risks / open questions

- **HTML structure may change** — detail-page parsing is more brittle than RSS. Keep `parse_detail` tolerant (return None per-field on miss, never crash a run).
- **Terms of use / rate limits** — confirm scraping detail pages is acceptable; the conservative throttle above is the mitigation. If volume is ever a concern, enrichment can be made opt-in or slowed further.
- **International jobs** — a meaningful share are overseas (e.g. Hong Kong); "region" needs an explicit International bucket so the UK map isn't skewed.

## Rough effort

~half a day: schema migration + detail fetcher/parser + region map + rate-limited wiring + backfill script + fixtures. Un-pausing the 4 charts and adding the regional map is then trivial since the chart builders already exist.
