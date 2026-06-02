# Changelog

All notable changes to this project are recorded here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/). Dates are UTC.

## [Unreleased]

### Added
- **Detail-page enrichment pipeline.** `scraper/detail.py` fetches each job's
  detail page and parses the schema.org `JobPosting` JSON-LD block to recover
  closing date, contract type, hours, and location/region (UK nation or
  "International") — fields the RSS feed omits. New `location`, `region`, and
  `enriched_at` columns; `jobs_needing_enrichment` / `update_enrichment` queries;
  rate-limited `run_enrichment` (sequential, delayed, skips already-enriched).
  Wired into `scraper.run` (capped at 200/run, `--no-enrich` to skip) and a
  `scripts/enrich_backfill` script for the historical backlog. Tests in
  `tests/test_detail.py`.
- Project documentation: full `README.md`, `docs/architecture.md`,
  `docs/data-dictionary.md`, and this changelog.
- Git pre-commit hook (`.githooks/pre-commit`, enabled via `core.hooksPath`)
  that blocks commits which don't update `CHANGELOG.md`, with a documented
  `SKIP_CHANGELOG=1` bypass. Enable per clone with
  `git config core.hooksPath .githooks` (see README "Development").
- `.gitattributes` forcing LF line endings on shell scripts and hooks.

## [0.5.0] — 2026-06-02

### Added
- Three RSS-native charts that work with current data: salary transparency trend
  (% of postings hiding pay), salary floor distribution histogram, and a
  seniority-band breakdown inferred from title keywords (with median floor).
- `docs/detail-page-enrichment.md` scoping how to recover closing date, contract
  type, hours, and location by fetching job detail pages.

### Changed
- **Visual overhaul:** defined a light Streamlit theme, modernised the chart
  palette, larger left-aligned titles, high-contrast axis text, styled hover
  tooltips, gradient fills under key line charts, and rounded bar corners.
- Moved the lookback filter from the sidebar into a header popover and collapsed
  the sidebar, so charts span the full page width.
- Overview tab now shows charts above insights, with insights capped to the top 3
  (severity-sorted) and the rest behind an expander.
- Replaced the deprecated `use_container_width` Streamlit arg with `width=`.

### Removed
- Paused four charts whose source columns are never populated by the RSS feed
  (recruitment window, contract type, hours, permanent share). Builders retained
  for when detail-page enrichment lands.

### Documented
- Confirmed the jobs.ac.uk RSS feed only carries institution, department, and
  salary — `closing_date`, `contract_type`, `hours`, and location are absent.

## [0.4.0] — 2026-05-29

### Added
- Parser unit tests (`tests/test_parser.py`).
- `scripts/reparse.py` salary re-parse backfill.

## [0.3.0] — 2026-05-28

### Added
- Six advanced charts: seasonality heatmap, recruitment window, HHI market
  concentration, salary percentiles, keyword premium, permanent-contract share.

### Changed
- Reworked alerts into non-alarmist "business insights" terminology.
- Performance & correctness: optimised the bulk-upsert query (single `IN (...)`
  lookup), parallelised the scraper (`ThreadPoolExecutor`), fixed an index-creation
  ordering bug, and added custom dashboard CSS + Plotly styling.

## [0.2.0] — 2026-05-27

### Added
- Extended trend analysis and a 5-tab dashboard.
- Capture of closing date, contract type, and hours in the parser/schema
  (note: later found absent from the RSS feed — see 0.5.0).
- nginx reverse-proxy and TLS setup documented in the deploy scripts.
- Last-scraped timestamp in the sidebar (replacing a refresh button).

### Fixed
- Run `init_db()` at dashboard startup so schema migrations always apply.
- Unique `key=` on every `st.plotly_chart()` call.
- Five issues surfaced by code review.

## [0.1.0] — 2026-05-26

### Added
- Initial HE job market analysis stack: RSS scraper, SQLite persistence layer,
  analysis module, and Streamlit dashboard.
