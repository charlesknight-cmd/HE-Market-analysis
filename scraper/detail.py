"""Enrich jobs by parsing the schema.org JobPosting JSON-LD on each detail page.

The RSS feed only carries institution, department, and salary. Each job's detail
HTML page, however, embeds a `<script type="application/ld+json">` JobPosting
block with the closing date, employment type, and location. This module fetches
that page and extracts those fields.

robots.txt (checked 2026-06-02) allows /job/ pages. Be polite: fetch sequentially
with a delay and only for jobs that aren't already enriched.
"""

import html as _html
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit

import requests

from config import REQUEST_HEADERS, SALARY_CEILING, SALARY_FLOOR
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


def fetch_detail_page(url: str, session: requests.Session | None = None,
                      timeout: int = 20) -> tuple[str, str] | None:
    """Return (html, final_url) for a detail page, or None on any network/HTTP error.

    final_url matters: ~45 days after closing, jobs.ac.uk 302s an expired job to
    a /search/ page whose query string carries the job's discipline facets.
    """
    getter = session or requests
    try:
        resp = getter.get(url, headers=REQUEST_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text, resp.url
    except requests.RequestException:
        return None


def fetch_detail(url: str, session: requests.Session | None = None,
                 timeout: int = 20) -> str | None:
    """Return the detail-page HTML, or None on any network/HTTP error."""
    page = fetch_detail_page(url, session=session, timeout=timeout)
    return page[0] if page else None


# --- Subject areas (discipline tags) -----------------------------------------
#
# The detail page's sidebar lists every subject area a job is tagged with as a
# run of small GET forms, one per tag, each carrying the facet params as hidden
# inputs plus a submit button whose value is the display name:
#
#   <p><b>Subject Area(s):</b></p>
#   <form ...><input name="academicDisciplineFacet[0]" value="economics" type="hidden">
#             <input class="parent-category" type="submit" value="Economics"></form>
#   <form ...><input name="academicDisciplineFacet[0]" value="social-sciences-and-social-care" type="hidden">
#             <input name="subDisciplineFacet[0]" value="social-policy" type="hidden">
#             <input class="" type="submit" value="Social Policy"></form>
#   <form ...><input name="nonAcademicDisciplineFacet[0]" value="student-services" type="hidden">
#             <input class="parent-category" type="submit" value="Student Services"></form>
#   <p><b>Location(s):</b></p>
#
# Some pages also embed the same data as JSON (`"subjectAreas": [...]`), but not
# all do, so the form block is the one we parse.

_SUBJECT_BLOCK_RE = re.compile(
    r"Subject\s+Area\(s\):(.*?)(?:<p><b>[A-Z][^<]{0,40}:</b>|$)",
    re.DOTALL | re.IGNORECASE,
)
_FORM_RE = re.compile(r"<form\b[^>]*>(.*?)</form>", re.DOTALL | re.IGNORECASE)
_INPUT_RE = re.compile(r"<input\b([^>]*)>", re.IGNORECASE)
_ATTR_RE = re.compile(r"""([\w\[\]:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")

_FACET_KINDS = {
    "academicDisciplineFacet":    "academic",
    "subDisciplineFacet":         "sub",
    "nonAcademicDisciplineFacet": "non-academic",
}
_FACET_KEY_RE = re.compile(
    r"^(academicDisciplineFacet|subDisciplineFacet|nonAcademicDisciplineFacet)(?:\[\d*\])?$"
)


def _input_attrs(tag_body: str) -> dict[str, str]:
    return {m.group(1): _html.unescape(m.group(2) if m.group(2) is not None else (m.group(3) or ""))
            for m in _ATTR_RE.finditer(tag_body)}


def _facet_kind(param_name: str) -> str | None:
    m = _FACET_KEY_RE.match(param_name or "")
    return _FACET_KINDS[m.group(1)] if m else None


def _classify(facets: dict[str, str], name: str | None) -> dict | None:
    """Turn one form's facet params into a single {facet, slug, name, parent_slug} tag.

    A form with a sub-discipline param is that sub-discipline (its academic param
    is the parent). Otherwise it's the academic or non-academic discipline named.
    """
    if facets.get("sub"):
        return {"facet": "sub", "slug": facets["sub"], "name": name,
                "parent_slug": facets.get("academic")}
    for kind in ("academic", "non-academic"):
        if facets.get(kind):
            return {"facet": kind, "slug": facets[kind], "name": name, "parent_slug": None}
    return None


def _dedupe_with_positions(tags: list[dict]) -> list[dict]:
    """Drop repeat (facet, slug) pairs and number each facet's tags 0.. in page order."""
    seen: set[tuple[str, str]] = set()
    counters: dict[str, int] = {}
    out = []
    for t in tags:
        key = (t["facet"], t["slug"])
        if key in seen:
            continue
        seen.add(key)
        t["position"] = counters.get(t["facet"], 0)
        counters[t["facet"]] = t["position"] + 1
        out.append(t)
    return out


def parse_subject_areas(html: str) -> list[dict]:
    """Extract the job's subject-area tags from detail-page HTML.

    Returns [{facet, slug, name, parent_slug, position}, ...] in page order -
    facet is 'academic' (one of the 21 discipline facets we scrape), 'sub'
    (with parent_slug set to its academic discipline) or 'non-academic'. Empty
    list if the page has no Subject Area(s) block.
    """
    m = _SUBJECT_BLOCK_RE.search(html or "")
    if not m:
        return []
    tags = []
    for form_body in _FORM_RE.findall(m.group(1)):
        facets: dict[str, str] = {}
        name = None
        for tag_body in _INPUT_RE.findall(form_body):
            attrs = _input_attrs(tag_body)
            kind = _facet_kind(attrs.get("name", ""))
            if kind and attrs.get("value"):
                facets[kind] = attrs["value"].strip()
            elif attrs.get("type", "").lower() == "submit" and attrs.get("value"):
                name = attrs["value"].strip() or None
        tag = _classify(facets, name)
        if tag:
            tags.append(tag)
    return _dedupe_with_positions(tags)


def is_expired_redirect(final_url: str | None) -> bool:
    """True if a detail-page fetch landed on the expired-job search redirect."""
    if not final_url:
        return False
    parts = urlsplit(final_url)
    return parts.path.rstrip("/").endswith("/search") or "expired-job-redirect=true" in parts.query


def parse_redirect_disciplines(final_url: str) -> list[dict]:
    """Recover discipline tags from an expired-job redirect URL.

    The redirect target looks like
      /search/?academicDisciplineFacet[0]=law&subDisciplineFacet[0]=criminal-law
              &nonAcademicDisciplineFacet[0]=student-services&...&expired-job-redirect=true
    Display names aren't available, and a sub-discipline can't be tied to its
    parent when several academic facets are present, so parent_slug is only set
    when exactly one academic discipline is named.
    """
    if not final_url:
        return []
    tags = []
    for key, value in parse_qsl(urlsplit(final_url).query, keep_blank_values=False):
        kind = _facet_kind(key)
        if kind and value.strip():
            tags.append({"facet": kind, "slug": value.strip(), "name": None, "parent_slug": None})
    academics = [t["slug"] for t in tags if t["facet"] == "academic"]
    if len(academics) == 1:
        for t in tags:
            if t["facet"] == "sub":
                t["parent_slug"] = academics[0]
    return _dedupe_with_positions(tags)


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


def _parse_basesalary(job: dict) -> tuple[float | None, float | None]:
    """Return (min, max) annual GBP salary from the JSON-LD baseSalary block.

    Only GBP, annual (unitText YEAR) amounts within the plausible salary band
    (SALARY_FLOOR..SALARY_CEILING) are accepted, so foreign-currency, hourly,
    token, or misparsed values don't pollute the £ analytics.
    """
    bs = job.get("baseSalary")
    if not isinstance(bs, dict):
        return None, None
    if (bs.get("currency") or "GBP").upper() != "GBP":
        return None, None
    value = bs.get("value")
    if not isinstance(value, dict):
        return None, None
    unit = (value.get("unitText") or "YEAR").upper()
    if unit not in ("YEAR", "ANNUM", "ANNUAL"):
        return None, None

    def _num(x):
        try:
            f = float(x)
        except (TypeError, ValueError):
            return None
        return f if SALARY_FLOOR <= f <= SALARY_CEILING else None

    mn, mx = _num(value.get("minValue")), _num(value.get("maxValue"))
    if mn is None and mx is None:
        return None, None
    return (mn or mx), (mx or mn)


_EMPTY_DETAIL = {
    "closing_date": None, "contract_type": None, "hours": None,
    "location": None, "region": None, "date_posted": None,
    "salary_min": None, "salary_max": None,
}


def parse_detail(html: str) -> dict:
    """Extract enrichment fields from detail-page HTML.

    Returns closing_date, contract_type, hours, location, region, date_posted,
    and salary_min/salary_max (annual GBP from baseSalary). Any field that can't
    be found is None; all-None if there's no JobPosting block at all.
    """
    job = _extract_jobposting(html)
    if not job:
        return dict(_EMPTY_DETAIL)

    employment = job.get("employmentType") or ""
    location, region = _parse_location(job)
    salary_min, salary_max = _parse_basesalary(job)
    return {
        "closing_date":  _iso_to_date(job.get("validThrough")),
        "contract_type": _parse_contract_type(employment),
        "hours":         _parse_hours(employment),
        "location":      location,
        "region":        region,
        "date_posted":   _iso_to_date(job.get("datePosted")),
        "salary_min":    salary_min,
        "salary_max":    salary_max,
    }


def enrich_url(url: str, session: requests.Session | None = None) -> dict | None:
    """Fetch and parse one detail page. None if the page couldn't be fetched.

    Returns parse_detail's fields plus `disciplines` (see parse_subject_areas),
    `discipline_source` ('detail' or 'redirect') and `expired` (True when the
    site redirected to search because the job has aged out - no JobPosting
    fields are available then, only the disciplines encoded in the redirect).
    """
    page = fetch_detail_page(url, session=session)
    if page is None:
        return None
    html, final_url = page
    if is_expired_redirect(final_url):
        return {**_EMPTY_DETAIL, "disciplines": parse_redirect_disciplines(final_url),
                "discipline_source": "redirect", "expired": True}
    return {**parse_detail(html), "disciplines": parse_subject_areas(html),
            "discipline_source": "detail", "expired": False}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def run_enrichment(limit: int = 200, delay: float = 1.5, verbose: bool = True,
                   reenrich: bool = False) -> dict:
    """Enrich jobs politely and sequentially.

    Fetches at most `limit` jobs (newest first), sleeping `delay` seconds between
    requests. Network failures leave a job un-stamped so it's retried next run;
    a page that loads but has no JobPosting block is still stamped (no retry).
    reenrich=True re-fetches jobs missing date_posted (one-off field backfill).
    Returns {'attempted', 'enriched', 'failed'}.
    """
    # Imported here so the parser functions stay usable without a DB present.
    from db.queries import jobs_needing_enrichment, update_enrichment

    pending = jobs_needing_enrichment(limit=limit, reenrich=reenrich)
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
