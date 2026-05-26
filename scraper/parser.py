"""Parse raw feedparser entries into clean job dicts."""

import re
from html import unescape
from typing import Any


def extract_job_id(url: str) -> str | None:
    """Pull the job reference code from a jobs.ac.uk URL (e.g. 'DRR304')."""
    m = re.search(r"/job/([A-Z0-9]+)/", url, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def parse_description(raw_desc: str) -> dict[str, str | None]:
    """Extract institution, department, and raw salary string.

    The description field looks like:
        "Institution Name - Faculty / Department<br />Salary: £40,000 to £50,000"
    """
    desc = unescape(raw_desc or "")

    # Split on <br> variants to separate the location line from the salary line
    parts = re.split(r"<br\s*/?>", desc, flags=re.IGNORECASE)

    institution = department = salary_raw = None

    if parts:
        location_line = _strip_tags(parts[0])
        segments = [s.strip() for s in location_line.split(" - ") if s.strip()]
        if segments:
            institution = segments[0]
            if len(segments) > 1:
                department = " - ".join(segments[1:])

    for part in parts[1:]:
        clean = _strip_tags(part)
        if re.match(r"salary\s*:", clean, re.IGNORECASE):
            salary_raw = re.sub(r"(?i)^salary\s*:\s*", "", clean).strip().rstrip(".")
            break

    return {
        "institution": institution,
        "department": department,
        "salary_raw": salary_raw,
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
        "job_id":      job_id,
        "title":       title,
        "institution": parsed["institution"],
        "department":  parsed["department"],
        "salary_raw":  parsed["salary_raw"],
        "salary_min":  salary_min,
        "salary_max":  salary_max,
        "category":    category,
        "url":         url,
    }
