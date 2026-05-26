from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "jobs.db"

# jobs.ac.uk RSS feeds by job type — one entry per category
RSS_FEEDS = {
    "academic-or-research":       "https://www.jobs.ac.uk/jobs/academic-or-research/?format=rss",
    "professional-or-managerial": "https://www.jobs.ac.uk/jobs/professional-or-managerial/?format=rss",
    "technical":                  "https://www.jobs.ac.uk/jobs/technical/?format=rss",
    "clerical":                   "https://www.jobs.ac.uk/jobs/clerical/?format=rss",
    "further-education":          "https://www.jobs.ac.uk/jobs/further-education/?format=rss",
    "craft-or-manual":            "https://www.jobs.ac.uk/jobs/craft-or-manual/?format=rss",
}

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
