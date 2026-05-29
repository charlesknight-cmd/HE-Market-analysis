"""Unit tests for the pure parsing functions in scraper/parser.py.

These functions carry the most logic and are the most likely to silently rot as
jobs.ac.uk's feed formatting drifts. The fixtures below mirror the real
description shape:

    Institution - Faculty<br />Salary: £x to £y<br />Closing Date: ...<br />
    Contract Type: ...<br />Hours: ...
"""

from scraper.parser import (
    extract_job_id,
    parse_description,
    parse_salary,
    _parse_closing_date,
    _parse_contract_type,
    _parse_hours,
)


class TestExtractJobId:
    def test_standard_url(self):
        assert extract_job_id("https://www.jobs.ac.uk/job/DRR304/lecturer/") == "DRR304"

    def test_lowercase_is_uppercased(self):
        assert extract_job_id("https://www.jobs.ac.uk/job/abc123/role/") == "ABC123"

    def test_no_match_returns_none(self):
        assert extract_job_id("https://www.jobs.ac.uk/about/") is None

    def test_empty_string(self):
        assert extract_job_id("") is None


class TestParseSalary:
    def test_range(self):
        assert parse_salary("£40,000 to £50,000") == (40000.0, 50000.0)

    def test_single_value(self):
        assert parse_salary("£42,000") == (42000.0, 42000.0)

    def test_none_input(self):
        assert parse_salary(None) == (None, None)

    def test_empty_input(self):
        assert parse_salary("") == (None, None)

    def test_unparseable(self):
        assert parse_salary("Competitive") == (None, None)

    def test_hourly_rate_excluded(self):
        # Hourly figures must not be treated as annual salaries
        assert parse_salary("£15.50 per hour") == (None, None)

    def test_sub_threshold_excluded(self):
        # Values under £10,000 are treated as noise (e.g. stipends, fees)
        assert parse_salary("£5,000") == (None, None)

    def test_mixed_keeps_only_annual(self):
        assert parse_salary("£35,000 to £45,000 per annum") == (35000.0, 45000.0)


class TestParseClosingDate:
    def test_long_month(self):
        assert _parse_closing_date("15 June 2026") == "2026-06-15"

    def test_short_month(self):
        assert _parse_closing_date("3 Jun 2026") == "2026-06-03"

    def test_ordinal_suffix_stripped(self):
        assert _parse_closing_date("22nd June 2026") == "2026-06-22"
        assert _parse_closing_date("1st July 2026") == "2026-07-01"

    def test_slash_format(self):
        assert _parse_closing_date("15/06/2026") == "2026-06-15"

    def test_trailing_period(self):
        assert _parse_closing_date("15 June 2026.") == "2026-06-15"

    def test_unparseable_returns_none(self):
        assert _parse_closing_date("soon") is None


class TestParseContractType:
    def test_permanent(self):
        assert _parse_contract_type("Permanent") == "permanent"

    def test_fixed_term(self):
        assert _parse_contract_type("Fixed-term") == "fixed-term"

    def test_contract_synonyms(self):
        assert _parse_contract_type("Temporary") == "fixed-term"

    def test_unknown_returns_none(self):
        assert _parse_contract_type("Secondment") is None


class TestParseHours:
    def test_full_time(self):
        assert _parse_hours("Full Time") == "full-time"

    def test_part_time(self):
        assert _parse_hours("Part Time") == "part-time"

    def test_both_is_flexible(self):
        assert _parse_hours("Full Time or Part Time") == "flexible"

    def test_unknown_returns_none(self):
        assert _parse_hours("Shift work") is None


class TestParseDescription:
    def test_full_description(self):
        raw = (
            "University of Example - Faculty of Science<br />"
            "Salary: £40,000 to £50,000<br />"
            "Closing Date: 15 June 2026<br />"
            "Contract Type: Fixed-term<br />"
            "Hours: Full Time"
        )
        result = parse_description(raw)
        assert result["institution"] == "University of Example"
        assert result["department"] == "Faculty of Science"
        assert result["salary_raw"] == "£40,000 to £50,000"
        assert result["closing_date"] == "2026-06-15"
        assert result["contract_type"] == "fixed-term"
        assert result["hours"] == "full-time"

    def test_institution_only(self):
        result = parse_description("University of Example<br />Salary: £30,000")
        assert result["institution"] == "University of Example"
        assert result["department"] is None
        assert result["salary_raw"] == "£30,000"

    def test_first_salary_line_wins(self):
        # Guard against a second Salary: line overwriting the first
        raw = "Inst<br />Salary: £40,000<br />Salary: £99,000"
        assert parse_description(raw)["salary_raw"] == "£40,000"

    def test_div_and_p_tag_formatting(self):
        # Broadened split must handle <p>/<div> styles, not just <br>
        raw = "<p>Inst - Dept</p><p>Salary: £30,000</p>"
        result = parse_description(raw)
        assert result["institution"] == "Inst"
        assert result["department"] == "Dept"
        assert result["salary_raw"] == "£30,000"

    def test_html_entities_unescaped(self):
        result = parse_description("Smith &amp; Jones University<br />Salary: £30,000")
        assert result["institution"] == "Smith & Jones University"

    def test_empty_input(self):
        result = parse_description("")
        assert result["institution"] is None
        assert result["salary_raw"] is None
