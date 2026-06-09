from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "jobs.db"

# jobs.ac.uk retired its RSS feeds (~June 2026 — the old ?format=rss URLs now
# 500 or return HTML). We scrape the server-rendered search-results pages
# instead; they carry MORE than the old feed did (location, closing date and
# date placed are all in the listing). One entry per job-type category.
SEARCH_BASE = "https://www.jobs.ac.uk/search"
SEARCH_FEEDS = {
    slug: f"{SEARCH_BASE}/{slug}"
    for slug in (
        "academic-or-research",
        "professional-or-managerial",
        "technical",
        "clerical",
        "further-education",
        "craft-or-manual",
    )
}

# Pagination + politeness. jobs.ac.uk caps page size at 25 (larger values are
# ignored or return empty), so we step startIndex by PAGE_SIZE. Listings are
# sorted newest-first, so the daily scrape stops once it hits a page of jobs it
# already knows; MAX_PAGES_PER_CATEGORY only bounds the first post-outage catch-up.
PAGE_SIZE = 25
MAX_PAGES_PER_CATEGORY = 60
PAGE_DELAY = 1.0  # seconds between page requests (per category)

# Friendly display names for each category
CATEGORY_LABELS = {
    "academic-or-research":       "Academic / Research",
    "professional-or-managerial": "Professional / Managerial",
    "technical":                  "Technical",
    "clerical":                   "Clerical",
    "further-education":          "Further Education",
    "craft-or-manual":            "Craft / Manual",
}

# Time of day to run the daily scheduled scrape (24 h HH:MM)
SCHEDULE_TIME = "07:00"

# Alert thresholds used by the analysis module
ALERT_THRESHOLDS = {
    # Notify when a single institution posts this many jobs in a rolling 7-day window
    "institution_weekly_jobs": 5,
    # Notify when a category grows by this % week-on-week
    "category_growth_pct": 25,
}

REQUEST_HEADERS = {
    "User-Agent": "HE-Market-Analysis/1.0 (research project; contact via GitHub)"
}
