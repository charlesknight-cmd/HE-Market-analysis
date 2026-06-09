"""Parse jobs.ac.uk search-results HTML into clean job dicts.

jobs.ac.uk retired its RSS feeds, so we scrape the server-rendered
`/search/<category>` listing pages. Each result card carries the job title,
employer, department, location, salary, date placed and closing date — which
is more than the old feed provided. `parse_listing_html` turns one page of
HTML into a list of job dicts shaped exactly like the rest of the pipeline
expects (see `db.queries.bulk_upsert`).
"""

import re
from datetime import date, datetime, timedelta, timezone

from bs4 import BeautifulSoup


def extract_job_id(url: str) -> str | None:
    """Pull the job reference code from a jobs.ac.uk URL (e.g. 'DRR304')."""
    m = re.search(r"/job/([A-Z0-9]+)/", url, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _parse_closing_date(text: str) -> str | None:
    """Parse a closing date string to YYYY-MM-DD, or None if unparseable."""
    text = text.strip().rstrip(".")
    # Remove ordinal suffixes from numbers (e.g. 15th -> 15, 1st -> 1, 22nd -> 22)
    text = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)
    formats = ["%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y", "%B %d, %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _parse_contract_type(text: str) -> str | None:
    """Normalise contract type to 'permanent' or 'fixed-term'."""
    t = text.lower()
    if "permanent" in t:
        return "permanent"
    if any(x in t for x in ("fixed", "contract", "temporary", "temp")):
        return "fixed-term"
    return None


def _parse_hours(text: str) -> str | None:
    """Normalise hours to 'full-time', 'part-time', or 'flexible'."""
    t = text.lower()
    full = "full" in t
    part = "part" in t
    if full and part:
        return "flexible"
    if full:
        return "full-time"
    if part:
        return "part-time"
    return None


def _infer_listing_date(daymon: str, today: date, prefer: str) -> str | None:
    """Turn a year-less 'DD Mon' listing date into YYYY-MM-DD.

    The search listing prints dates without a year (e.g. "09 Jun"). We infer it
    from `today`:
      prefer='past'   — date placed is on/before today; if the day/month lands in
                        the future it must belong to last year.
      prefer='future' — closing/expiry date is on/after today; if it lands in the
                        past it must belong to next year.
    A couple of days' tolerance absorbs UTC/site-timezone skew.
    """
    daymon = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", daymon.strip(), flags=re.IGNORECASE)
    # Parse against an explicit leap year (2000) so we only read month/day and
    # avoid the "no year" deprecation; the real year is inferred below.
    parsed = None
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            parsed = datetime.strptime(f"{daymon} 2000", fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        return None

    def _make(year: int) -> date | None:
        try:
            return date(year, parsed.month, parsed.day)
        except ValueError:  # 29 Feb on a non-leap year
            return None

    d = _make(today.year)
    if d is None:
        return None
    if prefer == "past" and d > today + timedelta(days=2):
        d = _make(today.year - 1) or d
    elif prefer == "future" and d < today - timedelta(days=2):
        d = _make(today.year + 1) or d
    return d.strftime("%Y-%m-%d")


def parse_salary(salary_raw: str | None) -> tuple[float | None, float | None]:
    """Return (salary_min, salary_max) in pounds, or (None, None) if unparseable."""
    if not salary_raw:
        return None, None

    # Detect if the salary refers to an hourly rate
    is_hourly = any(x in salary_raw.lower() for x in ("hour", "hourly", "p/h", "per hr", "per hour"))

    amounts = re.findall(r"£([\d,]+)", salary_raw)
    values = []
    for a in amounts:
        try:
            val = float(a.replace(",", ""))
            # Exclude hourly rates or clear outliers (under £10,000 annual)
            if val < 10000 or is_hourly:
                continue
            values.append(val)
        except ValueError:
            pass

    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]
    return values[0], values[1]


_BASE_URL = "https://www.jobs.ac.uk"


def _clean(text: str | None) -> str | None:
    """Collapse internal whitespace and trim; empty -> None."""
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip() or None


def _div_text_after_label(card, label: str) -> str | None:
    """Return the text following a 'Label:' inside any <div> of the card.

    Several fields (Location, Date Placed) are bare <div>s of the form
    "Location: Oxford" with no distinguishing class, so we match on the label.
    """
    for div in card.find_all("div"):
        text = _clean(div.get_text(" ", strip=True))
        if text and text.lower().startswith(label.lower()):
            return _clean(text[len(label):].lstrip(" :"))
    return None


def parse_listing_card(card, category: str, today: date | None = None) -> dict | None:
    """Convert one `.j-search-result__result` element into a job dict."""
    today = today or datetime.now(timezone.utc).date()

    anchor = card.find("a", href=True)
    if not anchor:
        return None
    href = anchor["href"]
    url = _BASE_URL + href if href.startswith("/") else href
    job_id = extract_job_id(url)
    if not job_id:
        return None

    title = _clean(anchor.get_text(strip=True))

    dept_el = card.find(class_="j-search-result__department")
    department = _clean(dept_el.get_text(" ", strip=True)) if dept_el else None

    emp_el = card.find(class_="j-search-result__employer")
    institution = _clean(emp_el.get_text(" ", strip=True)) if emp_el else None

    location = _div_text_after_label(card, "Location:")

    salary_raw = None
    info_el = card.find(class_="j-search-result__info")
    if info_el:
        salary_raw = _clean(re.sub(
            r"(?i)^salary\s*:\s*", "", info_el.get_text(" ", strip=True)
        ))
        if salary_raw:
            salary_raw = salary_raw.rstrip(".") or None
        if salary_raw and salary_raw.lower() == "not specified":
            salary_raw = None

    placed = _div_text_after_label(card, "Date Placed:")
    date_posted = _infer_listing_date(placed, today, "past") if placed else None

    # Closing date lives in <div class="j-search-result__date"> as the last <span>
    # ("Closes"/"Expires" label first, then the "DD Mon" value).
    closing_date = None
    date_div = card.find("div", class_="j-search-result__date")
    if date_div:
        spans = date_div.find_all("span")
        if spans:
            closing_date = _infer_listing_date(spans[-1].get_text(strip=True), today, "future")

    salary_min, salary_max = parse_salary(salary_raw)

    return {
        "job_id":        job_id,
        "title":         title,
        "institution":   institution,
        "department":    department,
        "salary_raw":    salary_raw,
        "salary_min":    salary_min,
        "salary_max":    salary_max,
        "closing_date":  closing_date,
        "contract_type": None,   # not in the listing — filled by detail enrichment
        "hours":         None,   # not in the listing — filled by detail enrichment
        "location":      location,
        "region":        None,   # derived from JSON-LD by detail enrichment
        "date_posted":   date_posted,
        "category":      category,
        "url":           url,
    }


def parse_listing_html(html: str, category: str, today: date | None = None) -> list[dict]:
    """Parse one search-results page into a list of job dicts (skips junk cards)."""
    soup = BeautifulSoup(html or "", "html.parser")
    cards = soup.find_all(class_="j-search-result__result")
    jobs = []
    for card in cards:
        job = parse_listing_card(card, category, today)
        if job:
            jobs.append(job)
    return jobs
