import concurrent.futures
import feedparser
import requests

from config import REQUEST_HEADERS, RSS_FEEDS
from scraper.parser import parse_entry


def fetch_category(slug: str, url: str) -> tuple[list[dict], str | None]:
    """Fetch a single RSS feed. Returns (jobs, error_message_or_None)."""
    try:
        # Use requests so redirects are followed reliably before feedparser sees content
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as exc:
        return [], str(exc)

    if feed.get("bozo") and not feed.entries:
        return [], f"Feed parse error: {feed.bozo_exception}"

    jobs = []
    for entry in feed.entries:
        job = parse_entry(entry, slug)
        if job:
            jobs.append(job)

    return jobs, None


def fetch_all() -> dict[str, tuple[list[dict], str | None]]:
    """Fetch every configured RSS feed concurrently. Returns {slug: (jobs, error)}."""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(RSS_FEEDS)) as executor:
        future_to_slug = {
            executor.submit(fetch_category, slug, url): slug
            for slug, url in RSS_FEEDS.items()
        }
        for future in concurrent.futures.as_completed(future_to_slug):
            slug = future_to_slug[future]
            try:
                jobs, error = future.result()
                results[slug] = (jobs, error)
            except Exception as exc:
                results[slug] = ([], str(exc))
    return results
