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

# Connector words kept lowercase when prettifying a slug that has no explicit
# display name (matches how the legacy job-type names read, e.g. "Academic or
# Research").
_SLUG_SMALL_WORDS = {"and", "or", "of", "the", "inc", "a"}
# Tokens that should render fully uppercased rather than title-cased, so an
# acronym-bearing slug doesn't come out as "Uk Wide" / "It Services".
_SLUG_ACRONYMS = {"uk", "eu", "us", "it", "hr", "ict", "ai", "phd", "tefl", "stem"}


def discipline_label(slug: str) -> str:
    """Resolve a category slug to a human display name — the single source of truth.

    Known disciplines come straight from CATEGORY_LABELS; anything else (the old
    job-type slugs such as ``academic-or-research`` that still ride on
    pre-migration rows, or any unforeseen slug) is prettified into its readable
    form — ``academic-or-research`` -> ``Academic or Research`` — rather than
    leaking raw kebab-case into legends, axes, tables and alert messages. Shared
    by the dashboard (charts/app) and the analysis/alerts layer so they can never
    drift apart.
    """
    if slug in CATEGORY_LABELS:
        return CATEGORY_LABELS[slug]
    words = str(slug).replace("_", "-").replace("-", " ").split()
    if not words:
        return str(slug)
    return " ".join(
        w.upper() if w in _SLUG_ACRONYMS
        else w if (i and w in _SLUG_SMALL_WORDS)
        else w[:1].upper() + w[1:]
        for i, w in enumerate(words)
    )

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
