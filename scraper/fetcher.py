"""Fetch and parse one or all jobs.ac.uk RSS feeds."""

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
    """Fetch every configured RSS feed. Returns {slug: (jobs, error)}."""
    results = {}
    for slug, url in RSS_FEEDS.items():
        results[slug] = fetch_category(slug, url)
    return results
