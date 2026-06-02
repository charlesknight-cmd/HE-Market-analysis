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
- Geographic charts on the Institutions tab: jobs by UK nation / International
  (`region_bar`) and top hiring locations (`top_locations_bar`), backed by new
  `jobs_by_region` / `top_locations` queries.
- Charts exploiting the enriched data: time-on-market histogram
  (`application_window_hist`), upcoming-deadlines bar (`upcoming_deadlines_bar`),
  median salary by region (`salary_by_region_bar`), and median salary by contract
  type (`salary_by_contract_bar`). `date_posted`, `closing_date`, and region added
  to the Data tab table.
- UK choropleth map of postings by nation (`region_choropleth`), backed by a
  bundled `dashboard/assets/uk_nations.geojson` (merged from georgique/world-geojson,
  OGL-licensed ONS/OS data), and a region × category concentration heatmap
  (`region_category_heatmap` + `region_category_matrix` query).
- Project documentation: full `README.md`, `docs/architecture.md`,
  `docs/data-dictionary.md`, and this changelog.

### Changed
- Split the long Trends tab into four nested sub-tabs — Volume & Seasonality,
  Pay, Contracts, Timing — so each view is ~3 charts instead of 12-deep scrolling.
- Enrichment now also captures `date_posted` (JSON-LD `datePosted`) and fills
  salary gaps from JSON-LD `baseSalary` (GBP, annual, ≥£10k; gap-fill only, never
  overwriting an RSS-parsed value). Recruitment-window chart now measures the true
  advertised window (`closing_date − date_posted`) instead of `closing − first_seen`.
  Backfill old rows with `python -m scripts.enrich_backfill --all`.
- Region parsing: UK jobs with no nation in the markup are now labelled
  "UK (unspecified)" instead of leaking a bare "United Kingdom" country string.
- Un-paused the four charts that depend on enrichment data (contract type,
  permanent share, hours, recruitment window) now that those fields populate.
- `docs/detail-page-enrichment.md` marked implemented (JSON-LD approach);
  `docs/data-dictionary.md` updated for the new/now-populated columns and charts.
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
