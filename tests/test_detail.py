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
    _parse_advert_details,
    _listed_location_region,
    _site_region,
)


def _salary(currency="GBP", unit="YEAR", mn="40000", mx="50000"):
    return {"baseSalary": {"@type": "MonetaryAmount", "currency": currency,
            "value": {"@type": "StructuredValue", "unitText": unit,
                      "minValue": mn, "maxValue": mx}}}


def _place(locality, region="", country=""):
    return {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": locality,
            "addressRegion": region, "addressCountry": country}}


def _enhanced_page(location="Suzhou - China", hours="Full Time",
                   contract="Fixed-Term/Contract") -> str:
    """Minimal enhanced 'campaign-site' advert: no JSON-LD, an Advert Details table."""
    return f"""<html><head><link href="https://www.jobs.ac.uk/enhanced/campaign-site/x/css/style.css">
    </head><body><table><tr><th>Ignored:</th><td>outside the card</td></tr></table>
    <div id="advert-details" class="card"><div class="card-body">
    <h2 class="card-title">Advert Details</h2> <table>
    <tr> <th>Location:</th> <td> {location} </td> </tr>
    <tr> <th>Salary:</th> <td> &pound;50,253 to &pound;56,535 per annum </td> </tr>
    <tr> <th>Hours:</th> <td>{hours}</td> </tr>
    <tr> <th>Contract Type:</th> <td>{contract}</td> </tr>
    <tr> <th>Placed On:</th> <td>25th August 2026</td> </tr>
    </table></div></div></body></html>"""


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

    def test_single_dict_location(self):
        job = {"jobLocation": _INTERNATIONAL["jobLocation"][0]}
        assert _parse_location(job) == ("Hong Kong", "International")

    def test_uk_country_without_nation_is_unspecified(self):
        job = {"jobLocation": [_place("Harwell", country="United Kingdom")]}
        assert _parse_location(job) == ("Harwell", "UK (unspecified)")

    def test_mixed_uk_overseas_uses_site_bucket(self):
        # Real case DSP263: DTU PhD with Imperial, JSON-LD lists London first.
        job = {"jobLocation": [_place("London", "England", "United Kingdom"),
                               _place("Lyngby", country="Denmark")]}
        assert _parse_location(job, "Europe") == ("Lyngby", "International")
        assert _parse_location(job, "London") == ("London", "England")
        assert _parse_location(job, "South East England") == ("London", "England")

    def test_mixed_without_site_bucket_keeps_first(self):
        job = {"jobLocation": [_place("London", "England", "United Kingdom"),
                               _place("Lyngby", country="Denmark")]}
        assert _parse_location(job) == ("London", "England")
        assert _parse_location(job, "Somewhere new") == ("London", "England")

    def test_all_uk_multi_location_keeps_first(self):
        job = {"jobLocation": [_place("Canterbury Christ Church University Medway Campus",
                                      "England", "United Kingdom"),
                               _place("Canterbury", "England", "United Kingdom")]}
        assert _parse_location(job, "Europe") == (
            "Canterbury Christ Church University Medway Campus", "England")


class TestSiteRegion:
    def test_extracts_bucket(self):
        html = '..."job_types":[],"location":"Asia & Middle East","location_code":"cn","logos":false...'
        assert _site_region(html) == "Asia & Middle East"

    def test_absent_or_empty(self):
        assert _site_region("<html></html>") is None
        assert _site_region('"location":"","location_code":""') is None


class TestListedLocationRegion:
    def test_overseas_suffix(self):
        assert _listed_location_region("Suzhou - China") == ("Suzhou", "International")
        assert _listed_location_region("Auckland - New Zealand") == ("Auckland", "International")

    def test_bare_place_is_uk(self):
        assert _listed_location_region("Ayr") == ("Ayr", "UK (unspecified)")
        assert _listed_location_region("London, Stratford") == ("London, Stratford", "UK (unspecified)")

    def test_uk_suffix(self):
        assert _listed_location_region("Belfast - Northern Ireland") == ("Belfast", "Northern Ireland")
        assert _listed_location_region("Leeds - United Kingdom") == ("Leeds", "UK (unspecified)")

    def test_hyphenated_place_is_not_split(self):
        assert _listed_location_region("Stoke-on-Trent") == ("Stoke-on-Trent", "UK (unspecified)")

    def test_empty(self):
        assert _listed_location_region("") == (None, None)


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

    def test_enhanced_page_falls_back_to_advert_details(self):
        d = parse_detail(_enhanced_page())
        assert d == {"closing_date": None, "contract_type": "fixed-term", "hours": "full-time",
                     "location": "Suzhou", "region": "International", "date_posted": None,
                     "salary_min": None, "salary_max": None}

    def test_enhanced_uk_page(self):
        d = parse_detail(_enhanced_page(location="Ayr", hours="Part Time", contract="Permanent"))
        assert (d["location"], d["region"], d["hours"], d["contract_type"]) == (
            "Ayr", "UK (unspecified)", "part-time", "permanent")

    def test_mixed_locations_use_page_site_bucket(self):
        html = _page({"jobLocation": [_place("London", "England", "United Kingdom"),
                                      _place("Lyngby", country="Denmark")]})
        html += '<script>var j = {"location":"Europe","location_code":""};</script>'
        assert parse_detail(html)["region"] == "International"


class TestParseAdvertDetails:
    def test_no_table(self):
        assert _parse_advert_details("<html><body>nothing</body></html>") == {}

    def test_drops_unparseable_fields(self):
        assert _parse_advert_details(_enhanced_page(location="", hours="", contract="See advert")) == {}
