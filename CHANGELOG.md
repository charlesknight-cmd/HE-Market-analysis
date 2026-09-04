# Changelog

All notable changes to this project are recorded here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/). Dates are UTC.

## [Unreleased]

### Added
- **September 2026 dashboard review implemented** (`docs/dashboard-review-2026-09.md`):
  - Every windowed query now keys off `date_posted`; `first_seen` is provenance only.
  - Weekly series (`category_weekly_counts`, `contract_type_trend`, `hours_trend`,
    `institution_weekly_trend`) exclude the current partial ISO week and show the
    full history regardless of the lookback control, which now scopes only the
    cross-sectional charts (default 90 days). Week-on-week growth and its
    insights compare the last two complete weeks.
  - Discipline breakdowns skip `config.LEGACY_JOB_TYPE_SLUGS`.
  - PhD studentships (`trends.is_studentship`) are excluded from every
    fixed-term share: the precarity chart, the PNG script, the headline
    permanent share and the sub-discipline drill-downs. Market fixed-term share
    moves from 62% to 58%.
  - Seniority classifier second pass (plural lecturers, lectureships, SL/AP,
    teaching fellows/tutors/teachers as their own band, open-rank faculty,
    fellowships, research scientists, professional-services vocabulary):
    unclassified titles fall from 1,323 to 273 of ~7,000.
  - New: `headline_stats` (Overview figures), `salary_by_discipline` +
    `salary_by_discipline_bar`, `subdiscipline_breakdown` /
    `nonacademic_breakdown` + `tag_breakdown_bar` (Roles drill-downs over the
    89 sub-discipline and 20 professional-services tags), `attribution_counts`
    + `attribution_dumbbell` (Data tab), `data_coverage` (fill-rate metrics).
    International dropped from the salary-by-region bar.
  - Tabs reorganised: Overview · Trends · Pay · Contracts & Timing · Roles ·
    Institutions (Recruiters / Geography) · Data. 29 charts plus headline
    figures, down from 43.
- **`scripts/attribution_chart.py`** — dumbbell PNG of adverts per discipline
  counted once (first-listed subject) versus under every subject they carry,
  with the ratio per row; the companion to `docs/linkedin-discipline-attribution.md`.
- **Precarity-by-discipline chart on the dashboard** (Trends › Contracts):
  `precarity_mix_bar` shows each discipline's fixed-term share against the
  all-adverts line, coloured by recruitment mix — research-heavy, balanced or
  teaching-heavy, from research-vs-lecturer titles — via
  `trends.recruitment_mix_by_discipline`. The title classifiers and the
  balanced band live in `analysis/trends.py` and are shared with the PNG script.
  `config.LEGACY_JOB_TYPE_SLUGS` names the retired job-type slugs so
  discipline analyses can skip them.
- **`scripts/casualisation_chart.py`** — renders the "precarity by discipline" PNG
  (fixed-term share per discipline vs the all-adverts baseline, coloured by
  research-heavy / balanced / teaching-heavy recruitment mix) for sharing outside
  the dashboard. Reads `jobs_by_discipline`; needs matplotlib (not in
  requirements.txt). Output goes to the gitignored `reports/`.
- **Multi-discipline attribution.** A job on jobs.ac.uk can be tagged with
  several of the 21 subject disciplines, but `jobs.category` only ever held the
  facet the scraper scanned first (alphabetical), which skewed every
  discipline-level chart. New `job_disciplines` table stores every tag — the 21
  academic disciplines, their sub-disciplines and the non-academic disciplines —
  captured from the detail page's "Subject Area(s)" block during enrichment
  (`scraper.detail.parse_subject_areas`), from the expired-job redirect URL for
  jobs whose page has aged out (`parse_redirect_disciplines`), and from every
  listing scan a job turns up in. Two views, `jobs_by_discipline` (one row per
  job × discipline) and `jobs_primary_discipline` (one row per job, first-listed
  discipline), replace `FROM jobs` in the discipline queries. `python -m
  scripts.backfill_disciplines` fills historic rows (newest-closing first;
  `--status` for coverage). The raw-jobs table filter now matches any of a job's
  disciplines. `tests/test_disciplines.py` covers the parsers, the upsert
  authority order, the views and the query helpers.
- **Nine new charts** exploiting the now ~3-month `date_posted` history and the
  high enrichment fill rates (closing_date/location/date_posted ~100%,
  contract/hours/region ~96%):
  - **Posting volume by true posting date** (Trends › Volume) — daily count +
    7-day average over `date_posted`, with the early window dimmed (survivorship
    undercount) and the last day or two flagged provisional.
  - **Weekday posting cadence** (Trends › Volume) — postings by day of week.
  - **Salary-transparency gap by discipline & region** (Trends › Pay) — % of
    postings with no parseable salary vs the overall baseline (the NULL is the
    signal, so this is immune to the 82% salary fill rate).
  - **Casualisation league table** (Trends › Contracts) — fixed-term share per
    discipline, diverging from the market baseline (min 40 contracted roles).
  - **Precarity matrix** (Trends › Contracts) — contract-type × hours heatmap
    with the fixed-term + part-time cell highlighted.
  - **Days-to-apply benchmark by discipline** (Trends › Timing) — median + IQR
    application window (`closing_date − date_posted`) per discipline.
  - **Deadline-pressure pipeline** (Trends › Timing) — open jobs bucketed by
    days-to-close on a red→green urgency ramp.
  - **Recruiter concentration** (Institutions › Recruiters) — Lorenz curve with
    Gini and top-10 share.
  - **International vs UK structural profile** (Institutions › Geography) —
    share-based contract/hours/disclosure comparison (never a non-GBP £ value).
  Each query keys off `date_posted` (no scraper-launch spike) and group-level
  cuts apply a min-N gate; all are covered by smoke-test cases and unit tests.
- **Colour-vision-deficiency-safe chart palette.** Replaced Plotly's
  Light24+Dark24 (many CVD-collapsing pairs) with an Okabe-Ito-derived 12-colour
  palette, extended via a CVD-floor-maximising search; worst-case CIELAB ΔE is
  16.05 under tritanopia across the whole set (independently verified with the
  Machado-2009 and Viénot-1999 models), so every folded top-8 discipline subset
  stays distinguishable while colours remain stable per discipline.
- **`config.discipline_label`** — a single source of truth for slug→display name.
  Legacy job-type slugs (`academic-or-research` …) now humanise to
  "Academic or Research" everywhere (legends, axes, tables, alerts, the report
  CLI) instead of leaking raw kebab-case; acronyms (UK, EU, IT) upper-case.
- **Conservative singular/plural folding** for the title-word and keyword-premium
  charts (`lecturer`+`lecturers` aggregate; a blocklist + suffix guards keep
  `studies`, `analyses`, `physics`, `campus`, … from being mangled). Location
  tokens (`london`, `uk`) are dropped from those charts.
- Per-tab orientation captions and the active lookback window shown in the header.
- Unit tests: `tests/test_stemming.py`, `tests/test_labels.py`.

### Removed
- Sixteen charts and their queries, per the September review: `daily_jobs_line`,
  `seasonal_heatmap`, `seasonal_bar`, `salary_inflation_line`,
  `salary_percentile_bands`, `salary_transparency_line`, `permanent_ratio_line`,
  `recruitment_window_line`, `market_concentration_line`, `new_vs_repeat_bar`,
  `longevity_histogram`, `category_growth_bar`, `salary_box_by_category`,
  `keyword_premium_bar`, `title_frequency_bar`, `region_choropleth` (and the
  title-stemming helpers and `tests/test_stemming.py` that only they used).
- The **casualisation league table** (`casualisation_by_discipline_bar` and its
  `fixed_term_share_by_discipline` query): superseded by the precarity-by-
  discipline chart, which shows the same fixed-term shares plus the recruitment
  mix that explains them.

### Changed
- Discipline-level analytics (weekly/monthly counts, share, growth, salary by
  discipline, seasonality heatmap, region × discipline, disclosure gap,
  casualisation, days-to-apply, institution discipline counts and spike lists)
  now count a multi-discipline job under each of its disciplines; "share" is
  share of discipline tags. Per-job distributions (salary histogram,
  keyword-premium baselines) use the job's first-listed discipline instead of
  the first-scanned facet. Institution spike counts are distinct jobs, not tags.
- `enrich_url` returns `disciplines`, `discipline_source` and `expired`
  alongside the JSON-LD fields; `fetch_detail_page` exposes the final URL so an
  expired-job redirect can be recognised.
- Chart titles and axis labels are now uniformly sentence-case.
- "Categories" → "Disciplines" in the KPI, tables and filters (post-migration term).
- The "Other / Unclassified" seniority bar is muted so the non-answer stops
  reading as the headline; caption/annotation greys darkened for WCAG AA contrast;
  stacked-bar segments gain a thin white separator (a non-colour CVD aid) and the
  metric-card hover respects `prefers-reduced-motion`.

### Fixed
- **Database connections were never closed.** `db.schema.get_connection` is now
  a context manager that closes the connection on exit (still committing on
  success and rolling back on error). Previously every `with get_connection()`
  block leaked two file descriptors on Python 3.14, so any long loop of per-row
  writes — the discipline backfill died at ~500 jobs with "unable to open
  database file" — would exhaust the 1024-fd limit. Every caller already used
  the `with` form, so no call sites changed.
- **Startup crash when no `secrets.toml` exists.** `st.secrets.get("password", "")`
  raises `StreamlitSecretNotFoundError` (not `KeyError`) when secrets are absent,
  so the default never applied and the app failed to load; now guarded.
- Dropped £0 salary-floor parsing noise from the distribution histogram, the
  spurious `-1` tick on the longevity chart, a same-title singular+plural
  double-count in the keyword-premium chart, and zero-data UK nations silently
  vanishing from the discipline × region heatmap (columns are now stable).
- **UK choropleth map no longer renders as a blank square.** The map now uses
  Plotly's MapLibre `choroplethmap` trace (flat Web-Mercator) rather than the geo
  `choropleth` trace (spherical d3-geo). The geo trace's fill depends on polygon
  ring winding order, and which winding it wants differs across Plotly.js
  versions — so the earlier rewind, tuned for one version, still inverted the
  polygons (filling the whole frame = blank) under the Plotly.js that Streamlit
  actually bundles. MapLibre projects on a plane and is indifferent to winding,
  so the map renders reliably regardless of the bundled Plotly.js version.
  Centre/zoom are fitted to the geojson bounding box (clamped so the Shetland
  Isles don't shrink the mainland to a speck); nations with no postings are
  padded to zero and outlined in grey so they still show.
- **Institution "pay vs hiring volume" scatter is readable again.** Previously
  every institution carried an always-on text label, which overlapped into an
  illegible smear, names were clipped at the edges, and bubble size merely
  duplicated the y-axis. Now all institutions are plotted with uniform markers
  and full hover detail, only a few standouts (biggest recruiters, highest/lowest
  payers) are labelled directly, and labels are placed away from the nearest edge.

### Changed
- **UK GeoJSON cache keys on file mtime.** `_uk_geojson()` now reloads
  the boundary file when its modification time changes instead of holding
  the first-loaded copy for the life of the process, so an edit to the
  geojson is picked up on the next render rather than after a restart.

### Added
- **Chart smoke-test script** (`scripts/chart_smoke_test.py`): exercises
  every chart builder against the live database and reports which return
  placeholder "no data" figures vs real traces. Safe to run anytime.
- **Chart regression tests** (`tests/test_charts.py`): assert the map uses the
  winding-insensitive MapLibre trace, the fitted view sits over the UK,
  zero-padding of missing nations, the International-only placeholder, and that
  the institution scatter labels only a subset of its points.

### Added
- **Database backup script + nightly cron.** `scripts/backup_db.py` takes a
  consistent, gzipped snapshot of `data/jobs.db` via SQLite's online backup API
  (WAL-aware, safe to run while the scraper writes) into `backups/` (gitignored),
  and prunes snapshots older than 30 days. Wired into a nightly server cron at
  06:00 UTC. The repo backs up code; this protects the collected data, which
  lives only on the server.

### Changed
- **Dashboard tuned for the 21-discipline taxonomy.** Replaced the 6-colour
  job-type palette with a 48-hue qualitative map keyed across all disciplines
  (+ legacy slugs), so category charts are no longer all-grey. The busy
  multi-category charts now fold the long tail into an "Other disciplines"
  bucket beyond the top 8 (weekly/monthly stacked bars, share-over-time area);
  the salary-by-discipline line chart shows only the best-represented
  disciplines; the region × category heatmap is transposed (disciplines down the
  y-axis, regions across) for legibility. Added a dismissible "Update — June 2026"
  note on the dashboard explaining the source/taxonomy change to users.
- **Category model rebuilt on subject disciplines.** jobs.ac.uk also dropped its
  six job-type category routes (~June 2026): `/search/academic-or-research`,
  `/search/technical`, … now all return the *same* unfiltered list. The live
  taxonomy is 21 subject **disciplines** (Biological Sciences, Computer Sciences,
  Engineering & Technology, …), filtered via the search facet
  `academicDisciplineFacet[]=<slug>`. The scraper now fetches one discipline at a
  time through that facet (`config.DISCIPLINES`), and the `category` column /
  dashboard category dimension holds the discipline slug. The facet rides in
  every request URL (including pagination), so requests are self-describing and
  immune to jobs.ac.uk's per-IP search state — earlier attempts to page the
  job-type slugs concurrently bled categories together. Pre-migration rows keep
  their old job-type `category` and age out. `config.SEARCH_FEEDS` (job-type) →
  `config.DISCIPLINES`; `CATEGORY_LABELS` now maps discipline slugs to names.
- **Data source migrated from RSS to search-results HTML.** jobs.ac.uk retired
  its RSS feeds (~June 2026): the old `?format=rss` URLs now return HTTP 500 or
  an HTML page, so the daily scrape had been recording `0 jobs` since 2026-06-07.
  `scraper/fetcher.py` and `scraper/parser.py` now fetch and parse the
  server-rendered `/search/<category>` listing pages instead (BeautifulSoup
  replaces feedparser). The listing is richer than the old feed: `location`,
  `closing_date`, and `date_posted` are parsed straight from each result card
  (year inferred for the year-less listing dates), so they no longer depend on
  detail-page enrichment — only `contract_type`, `hours`, and `region` still do.
  Pagination is session-based: page 1 hits `/search/<category>` (which stores the
  category in the server-side session), and later pages hit `/search/?startIndex=N`
  (no category in the path) on the same `requests.Session`, relying on the session
  cookie — `startIndex` is ignored on the pretty category path. Page size is 25
  (the site's max). Listings are date-sorted so the daily run stops once it reaches
  already-seen jobs; `scraper.run --full` disables that early-stop and pages to
  `config.MAX_PAGES_PER_CATEGORY` for the one-off post-outage catch-up.
  `config.RSS_FEEDS` → `config.SEARCH_FEEDS`; `bulk_upsert` now persists/gap-fills
  location, region, date_posted and salary; new `existing_job_ids` query feeds the
  incremental stop. Parser/fetcher tests cover the HTML cards and URL scheme;
  `feedparser` dropped from requirements, `beautifulsoup4` added.

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
- Split the Roles tab into two nested sub-tabs — Role Types and Salaries.
- Split the Institutions tab into three nested sub-tabs — Recruiters, Geography,
  and Dynamics.
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
