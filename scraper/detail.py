"""Enrich jobs by parsing the schema.org JobPosting JSON-LD on each detail page.

The RSS feed only carries institution, department, and salary. Each job's detail
HTML page, however, embeds a `<script type="application/ld+json">` JobPosting
block with the closing date, employment type, and location. This module fetches
that page and extracts those fields.

robots.txt (checked 2026-06-02) allows /job/ pages. Be polite: fetch sequentially
with a delay and only for jobs that aren't already enriched.
"""

import json
import re
import time
from datetime import datetime, timezone

import requests

from config import REQUEST_HEADERS
from scraper.parser import _parse_contract_type, _parse_hours

_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

# Country strings that count as the UK (otherwise the job is treated as International).
_UK_COUNTRIES = {
    "united kingdom", "uk", "gb", "great britain",
    "england", "scotland", "wales", "northern ireland",
}


def fetch_detail(url: str, session: requests.Session | None = None,
                 timeout: int = 20) -> str | None:
    """Return the detail-page HTML, or None on any network/HTTP error."""
    getter = session or requests
    try:
        resp = getter.get(url, headers=REQUEST_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


def _extract_jobposting(html: str) -> dict | None:
    """Pull the first JobPosting JSON-LD object out of the page, if present."""
    for raw in _JSONLD_RE.findall(html or ""):
        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        # JSON-LD may be a single object or a @graph list.
        candidates = data if isinstance(data, list) else data.get("@graph", [data])
        for obj in candidates:
            if isinstance(obj, dict) and obj.get("@type") == "JobPosting":
                return obj
    return None


def _iso_to_date(value: str | None) -> str | None:
    """'2026-06-07T00:00:00+00:00' -> '2026-06-07'."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d")
    except ValueError:
        # Fall back to a leading YYYY-MM-DD if the suffix is malformed.
        m = re.match(r"(\d{4}-\d{2}-\d{2})", value)
        return m.group(1) if m else None


def _parse_location(job: dict) -> tuple[str | None, str | None]:
    """Return (location, region) from the JobPosting jobLocation block."""
    loc = job.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if not isinstance(loc, dict):
        return None, None
    addr = loc.get("address") or {}
    if not isinstance(addr, dict):
        return None, None

    locality = (addr.get("addressLocality") or "").strip() or None
    region_raw = (addr.get("addressRegion") or "").strip()
    country = (addr.get("addressCountry") or "").strip()

    _UK_NATIONS = {"england", "scotland", "wales", "northern ireland"}
    if country and country.lower() not in _UK_COUNTRIES:
        region = "International"
    elif region_raw.lower() in _UK_NATIONS:
        region = region_raw
    elif locality or country:
        # UK job with no nation in the markup — don't leak a bare country string.
        region = "UK (unspecified)"
    else:
        region = None
    return locality, region


def parse_detail(html: str) -> dict:
    """Extract enrichment fields from detail-page HTML.

    Returns a dict with keys closing_date, contract_type, hours, location, region.
    Any field that can't be found is None. An empty dict's worth of Nones is
    returned if there's no JobPosting block at all.
    """
    job = _extract_jobposting(html)
    if not job:
        return {"closing_date": None, "contract_type": None, "hours": None,
                "location": None, "region": None}

    employment = job.get("employmentType") or ""
    location, region = _parse_location(job)
    return {
        "closing_date":  _iso_to_date(job.get("validThrough")),
        "contract_type": _parse_contract_type(employment),
        "hours":         _parse_hours(employment),
        "location":      location,
        "region":        region,
    }


def enrich_url(url: str, session: requests.Session | None = None) -> dict | None:
    """Fetch and parse one detail page. None if the page couldn't be fetched."""
    html = fetch_detail(url, session=session)
    if html is None:
        return None
    return parse_detail(html)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def run_enrichment(limit: int = 200, delay: float = 1.5, verbose: bool = True) -> dict:
    """Enrich jobs that haven't been enriched yet, politely and sequentially.

    Fetches at most `limit` jobs (newest first), sleeping `delay` seconds between
    requests. Network failures leave a job un-stamped so it's retried next run;
    a page that loads but has no JobPosting block is still stamped (no retry).
    Returns {'attempted', 'enriched', 'failed'}.
    """
    # Imported here so the parser functions stay usable without a DB present.
    from db.queries import jobs_needing_enrichment, update_enrichment

    pending = jobs_needing_enrichment(limit=limit)
    stats = {"attempted": 0, "enriched": 0, "failed": 0}
    if not pending:
        if verbose:
            print("Enrichment: nothing pending.")
        return stats

    total = len(pending)
    if verbose:
        print(f"Enrichment: {total} job(s) to process (delay {delay}s)...")

    session = requests.Session()
    for i, job in enumerate(pending, 1):
        stats["attempted"] += 1
        data = enrich_url(job["url"], session=session)
        if data is None:
            stats["failed"] += 1
        else:
            update_enrichment(job["job_id"], data)
            stats["enriched"] += 1
        if verbose:
            tag = "ok" if data else "FAIL"
            print(f"  [{i}/{total}] {job['job_id']} -> {tag}")
        if i < total:
            time.sleep(delay)

    if verbose:
        print(f"Enrichment done: {stats['enriched']} enriched, {stats['failed']} failed.")
    return stats
