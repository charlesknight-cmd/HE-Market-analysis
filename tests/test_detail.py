"""Unit tests for the detail-page JSON-LD parsing in scraper/detail.py.

These mirror the real schema.org JobPosting shape jobs.ac.uk embeds in a
`<script type="application/ld+json">` block. They guard against silent rot if
that markup drifts.
"""

import json

from scraper.detail import (
    parse_detail,
    _extract_jobposting,
    _iso_to_date,
    _parse_location,
    _parse_basesalary,
)


def _salary(currency="GBP", unit="YEAR", mn="40000", mx="50000"):
    return {"baseSalary": {"@type": "MonetaryAmount", "currency": currency,
            "value": {"@type": "StructuredValue", "unitText": unit,
                      "minValue": mn, "maxValue": mx}}}


def _page(jobposting: dict) -> str:
    """Wrap a JobPosting dict in a minimal HTML page with a JSON-LD block."""
    blob = json.dumps({"@context": "https://schema.org", "@type": "JobPosting", **jobposting})
    return f"<html><head><script type=\"application/ld+json\">{blob}</script></head><body></body></html>"


_UK_FULLTIME_PERM = {
    "title": "Lecturer in Health and Social Care",
    "validThrough": "2026-06-07T00:00:00+00:00",
    "employmentType": "Full Time,Permanent",
    "jobLocation": [{"@type": "Place", "address": {
        "@type": "PostalAddress", "addressLocality": "Nottingham",
        "addressRegion": "England", "addressCountry": "United Kingdom"}}],
}

_INTERNATIONAL = {
    "title": "Professor",
    "validThrough": "2026-07-01T00:00:00+00:00",
    "employmentType": "Full Time,Fixed-Term/Contract",
    "jobLocation": [{"@type": "Place", "address": {
        "@type": "PostalAddress", "addressLocality": "Hong Kong",
        "addressRegion": "", "addressCountry": "Hong Kong"}}],
}


class TestIsoToDate:
    def test_strips_time_and_tz(self):
        assert _iso_to_date("2026-06-07T00:00:00+00:00") == "2026-06-07"

    def test_none(self):
        assert _iso_to_date(None) is None

    def test_malformed_falls_back_to_leading_date(self):
        assert _iso_to_date("2026-06-07 garbage") == "2026-06-07"


class TestExtractJobposting:
    def test_finds_block(self):
        job = _extract_jobposting(_page(_UK_FULLTIME_PERM))
        assert job and job["title"] == "Lecturer in Health and Social Care"

    def test_handles_graph_wrapper(self):
        blob = json.dumps({"@context": "https://schema.org",
                           "@graph": [{"@type": "WebSite"}, {"@type": "JobPosting", "title": "X"}]})
        html = f'<script type="application/ld+json">{blob}</script>'
        assert _extract_jobposting(html)["title"] == "X"

    def test_no_jsonld_returns_none(self):
        assert _extract_jobposting("<html><body>no script</body></html>") is None

    def test_malformed_json_is_skipped(self):
        assert _extract_jobposting('<script type="application/ld+json">{bad json}</script>') is None


class TestParseLocation:
    def test_uk_uses_region(self):
        assert _parse_location(_UK_FULLTIME_PERM) == ("Nottingham", "England")

    def test_non_uk_is_international(self):
        assert _parse_location(_INTERNATIONAL) == ("Hong Kong", "International")

    def test_missing_location(self):
        assert _parse_location({"title": "x"}) == (None, None)


class TestParseBaseSalary:
    def test_annual_gbp(self):
        assert _parse_basesalary(_salary()) == (40000.0, 50000.0)

    def test_non_gbp_rejected(self):
        assert _parse_basesalary(_salary(currency="USD")) == (None, None)

    def test_hourly_rejected(self):
        assert _parse_basesalary(_salary(unit="HOUR", mn="15", mx="20")) == (None, None)

    def test_sub_threshold_rejected(self):
        assert _parse_basesalary(_salary(mn="500", mx="900")) == (None, None)

    def test_single_value_mirrors(self):
        assert _parse_basesalary(_salary(mn="42000", mx=None)) == (42000.0, 42000.0)

    def test_missing_block(self):
        assert _parse_basesalary({"title": "x"}) == (None, None)


class TestParseDetail:
    def test_uk_fulltime_permanent(self):
        d = parse_detail(_page({**_UK_FULLTIME_PERM, "datePosted": "2026-05-26T00:00:00+00:00", **_salary()}))
        assert d == {
            "closing_date": "2026-06-07",
            "contract_type": "permanent",
            "hours": "full-time",
            "location": "Nottingham",
            "region": "England",
            "date_posted": "2026-05-26",
            "salary_min": 40000.0,
            "salary_max": 50000.0,
        }

    def test_international_fixed_term(self):
        d = parse_detail(_page(_INTERNATIONAL))
        assert d["contract_type"] == "fixed-term"
        assert d["hours"] == "full-time"
        assert d["region"] == "International"
        assert d["location"] == "Hong Kong"

    def test_no_jobposting_returns_all_none(self):
        d = parse_detail("<html><body>nothing here</body></html>")
        assert d == {"closing_date": None, "contract_type": None, "hours": None,
                     "location": None, "region": None, "date_posted": None,
                     "salary_min": None, "salary_max": None}
