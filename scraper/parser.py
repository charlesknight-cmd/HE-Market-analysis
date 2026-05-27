"""Parse raw feedparser entries into clean job dicts."""

import re
from datetime import datetime
from html import unescape
from typing import Any


def extract_job_id(url: str) -> str | None:
    """Pull the job reference code from a jobs.ac.uk URL (e.g. 'DRR304')."""
    m = re.search(r"/job/([A-Z0-9]+)/", url, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_closing_date(text: str) -> str | None:
    """Parse a closing date string to YYYY-MM-DD, or None if unparseable."""
    text = text.strip().rstrip(".")
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


def parse_description(raw_desc: str) -> dict[str, str | None]:
    """Extract institution, department, salary, closing date, contract type, and hours.

    The description field looks like:
        Institution Name - Faculty<br />Salary: £40,000 to £50,000<br />
        Closing Date: 15 June 2026<br />Contract Type: Fixed-term<br />Hours: Full Time
    """
    desc = unescape(raw_desc or "")

    # Split on <br> variants to get individual lines
    parts = re.split(r"<br\s*/?>", desc, flags=re.IGNORECASE)

    institution = department = salary_raw = None
    closing_date = contract_type = hours = None

    if parts:
        location_line = _strip_tags(parts[0])
        segments = [s.strip() for s in location_line.split(" - ") if s.strip()]
        if segments:
            institution = segments[0]
            if len(segments) > 1:
                department = " - ".join(segments[1:])

    for part in parts[1:]:
        clean = _strip_tags(part)
        cl = clean.lower()

        if re.match(r"salary\s*:", cl):
            salary_raw = re.sub(r"(?i)^salary\s*:\s*", "", clean).strip().rstrip(".")

        elif re.match(r"closing\s*date\s*:", cl):
            val = re.sub(r"(?i)^closing\s*date\s*:\s*", "", clean).strip()
            closing_date = _parse_closing_date(val)

        elif re.match(r"contract\s*(type)?\s*:", cl):
            val = re.sub(r"(?i)^contract\s*(type)?\s*:\s*", "", clean).strip()
            contract_type = _parse_contract_type(val)

        elif re.match(r"hours?\s*:", cl):
            val = re.sub(r"(?i)^hours?\s*:\s*", "", clean).strip()
            hours = _parse_hours(val)

    return {
        "institution":   institution,
        "department":    department,
        "salary_raw":    salary_raw,
        "closing_date":  closing_date,
        "contract_type": contract_type,
        "hours":         hours,
    }


def parse_salary(salary_raw: str | None) -> tuple[float | None, float | None]:
    """Return (salary_min, salary_max) in pounds, or (None, None) if unparseable."""
    if not salary_raw:
        return None, None

    amounts = re.findall(r"£([\d,]+)", salary_raw)
    values = []
    for a in amounts:
        try:
            values.append(float(a.replace(",", "")))
        except ValueError:
            pass

    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]
    return values[0], values[1]


def parse_entry(entry: Any, category: str) -> dict | None:
    """Convert a feedparser entry to a job dict ready for DB insertion."""
    url = entry.get("link", "")
    job_id = extract_job_id(url)
    if not job_id:
        return None

    title = entry.get("title", "").strip()
    desc = entry.get("summary", "") or entry.get("description", "")

    parsed = parse_description(desc)
    salary_min, salary_max = parse_salary(parsed["salary_raw"])

    return {
        "job_id":        job_id,
        "title":         title,
        "institution":   parsed["institution"],
        "department":    parsed["department"],
        "salary_raw":    parsed["salary_raw"],
        "salary_min":    salary_min,
        "salary_max":    salary_max,
        "closing_date":  parsed["closing_date"],
        "contract_type": parsed["contract_type"],
        "hours":         parsed["hours"],
        "category":      category,
        "url":           url,
    }
