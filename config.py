from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "jobs.db"

# jobs.ac.uk retired its RSS feeds AND its old job-type category routes (~June
# 2026): the old ?format=rss URLs now 500/return HTML, and the six job-type
# slugs (/search/academic-or-research, …) all resolve to the same unfiltered
# list. The live taxonomy is now subject *disciplines*, filtered via the search
# facet `academicDisciplineFacet[]=<slug>`. We scrape one discipline at a time;
# the server-rendered cards carry title, employer, department, location, salary,
# date placed and closing date. The `category` column now holds the discipline.
SEARCH_BASE = "https://www.jobs.ac.uk/search"
DISCIPLINE_FACET = "academicDisciplineFacet[]"

# The 21 subject disciplines jobs.ac.uk exposes (slug -> display name). A job may
# appear under more than one; it is stored under whichever is scraped first.
DISCIPLINES = {
    "agriculture-food-and-veterinary":         "Agriculture, Food & Veterinary",
    "architecture-building-and-planning":      "Architecture, Building & Planning",
    "biological-sciences":                     "Biological Sciences",
    "business-and-management-studies":         "Business & Management Studies",
    "computer-sciences":                       "Computer Sciences",
    "creative-arts-and-design":                "Creative Arts & Design",
    "economics":                               "Economics",
    "education-studies-inc-tefl":              "Education Studies (inc. TEFL)",
    "engineering-and-technology":              "Engineering & Technology",
    "health-and-medical":                      "Health & Medical",
    "historical-and-philosophical-studies":    "Historical & Philosophical Studies",
    "information-management-and-librarianship": "Information Management & Librarianship",
    "languages-literature-and-culture":        "Languages, Literature & Culture",
    "law":                                     "Law",
    "mathematics-and-statistics":              "Mathematics & Statistics",
    "media-and-communications":                "Media & Communications",
    "physical-and-environmental-sciences":     "Physical & Environmental Sciences",
    "politics-and-government":                 "Politics & Government",
    "psychology":                              "Psychology",
    "social-sciences-and-social-care":         "Social Sciences & Social Care",
    "sport-and-leisure":                       "Sport & Leisure",
}

# Pagination + politeness. jobs.ac.uk caps page size at 25 (larger values are
# ignored or return empty), so we step startIndex by PAGE_SIZE. Listings are
# sorted newest-first, so the daily scrape stops once it hits a page of jobs it
# already knows; MAX_PAGES_PER_CATEGORY only bounds the first post-outage catch-up.
PAGE_SIZE = 25
MAX_PAGES_PER_CATEGORY = 60
PAGE_DELAY = 1.0  # seconds between page requests (per discipline)

# The dashboard/analysis "category" dimension is now the discipline.
CATEGORY_LABELS = DISCIPLINES

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
