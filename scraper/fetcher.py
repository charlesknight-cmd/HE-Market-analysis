import time
from urllib.parse import quote

import requests

from config import (
    DISCIPLINE_FACET,
    DISCIPLINES,
    MAX_PAGES_PER_CATEGORY,
    PAGE_DELAY,
    PAGE_SIZE,
    REQUEST_HEADERS,
    SEARCH_BASE,
)
from scraper.parser import parse_listing_html


def _page_url(discipline: str, start_index: int, page_size: int) -> str:
    """Build the search URL for one discipline + page.

    The discipline rides in the `academicDisciplineFacet[]` query param on every
    request, so each request is self-describing — unlike the bare
    `/search/?startIndex=` endpoint, it does not depend on per-IP search state
    and so can't be clobbered by other requests.
    """
    facet = quote(DISCIPLINE_FACET, safe="")  # academicDisciplineFacet%5B%5D
    return (
        f"{SEARCH_BASE}/?{facet}={discipline}"
        f"&sortOrder=1&pageSize={page_size}&startIndex={start_index}"
    )


def fetch_category(
    discipline: str,
    known_ids: set[str] | None = None,
    max_pages: int = MAX_PAGES_PER_CATEGORY,
    page_size: int = PAGE_SIZE,
    delay: float = PAGE_DELAY,
    session: requests.Session | None = None,
) -> tuple[list[dict], str | None]:
    """Scrape one discipline's search pages. Returns (jobs, error_or_None).

    Pages are fetched newest-first via the facet URL. Stops when a page yields no
    jobs (end of results), when `max_pages` is reached, or — if `known_ids` is
    supplied — as soon as a whole page is already in the DB (listings are
    date-sorted, so everything beyond is older and already seen). Jobs are tagged
    with the discipline slug as their `category`. Whatever was gathered before an
    error is still returned alongside the error.
    """
    sess = session or requests.Session()
    jobs: dict[str, dict] = {}
    start_index = 1

    try:
        for _ in range(max_pages):
            url = _page_url(discipline, start_index, page_size)
            resp = sess.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()

            page_jobs = parse_listing_html(resp.text, discipline)
            if not page_jobs:
                break

            for job in page_jobs:
                jobs.setdefault(job["job_id"], job)

            if known_ids is not None and all(j["job_id"] in known_ids for j in page_jobs):
                break

            start_index += page_size
            if delay:
                time.sleep(delay)
    except Exception as exc:
        return list(jobs.values()), str(exc)

    return list(jobs.values()), None


def fetch_all(known_ids: set[str] | None = None) -> dict[str, tuple[list[dict], str | None]]:
    """Scrape every discipline. Returns {discipline_slug: (jobs, error)}.

    Disciplines are fetched sequentially, each with a fresh session, to stay
    polite (one in-flight search at a time). The facet URLs are stateless, so
    ordering doesn't matter for correctness — only for load.
    """
    results = {}
    for slug in DISCIPLINES:
        try:
            results[slug] = fetch_category(slug, known_ids, session=requests.Session())
        except Exception as exc:
            results[slug] = ([], str(exc))
    return results
