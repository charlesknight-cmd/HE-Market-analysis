import concurrent.futures
import time

import requests

from config import (
    MAX_PAGES_PER_CATEGORY,
    PAGE_DELAY,
    PAGE_SIZE,
    REQUEST_HEADERS,
    SEARCH_FEEDS,
)
from scraper.parser import parse_listing_html


def fetch_category(
    slug: str,
    base_url: str,
    known_ids: set[str] | None = None,
    max_pages: int = MAX_PAGES_PER_CATEGORY,
    page_size: int = PAGE_SIZE,
    delay: float = PAGE_DELAY,
    session: requests.Session | None = None,
) -> tuple[list[dict], str | None]:
    """Scrape one category's search-results pages. Returns (jobs, error_or_None).

    Pages are fetched newest-first via ?pageSize=&startIndex=. Stops when a page
    yields no jobs (end of results), when `max_pages` is reached, or — if
    `known_ids` is supplied — as soon as a whole page is already in the DB
    (listings are date-sorted, so everything beyond is older and already seen).
    Whatever was gathered before an error is still returned alongside the error.
    """
    sess = session or requests.Session()
    jobs: dict[str, dict] = {}
    start_index = 1

    try:
        for _ in range(max_pages):
            url = f"{base_url}?pageSize={page_size}&startIndex={start_index}"
            resp = sess.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()

            page_jobs = parse_listing_html(resp.text, slug)
            if not page_jobs:
                break

            for job in page_jobs:
                jobs.setdefault(job["job_id"], job)

            # Incremental stop: a full page of already-known jobs means we've
            # caught up — no point paging deeper into older listings.
            if known_ids is not None and all(j["job_id"] in known_ids for j in page_jobs):
                break

            start_index += page_size
            if delay:
                time.sleep(delay)
    except Exception as exc:
        return list(jobs.values()), str(exc)

    return list(jobs.values()), None


def fetch_all(known_ids: set[str] | None = None) -> dict[str, tuple[list[dict], str | None]]:
    """Scrape every configured category concurrently. Returns {slug: (jobs, error)}."""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(SEARCH_FEEDS)) as executor:
        future_to_slug = {
            executor.submit(fetch_category, slug, url, known_ids): slug
            for slug, url in SEARCH_FEEDS.items()
        }
        for future in concurrent.futures.as_completed(future_to_slug):
            slug = future_to_slug[future]
            try:
                results[slug] = future.result()
            except Exception as exc:
                results[slug] = ([], str(exc))
    return results
