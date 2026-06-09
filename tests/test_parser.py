"""Unit tests for the pure parsing functions in scraper/parser.py.

These functions carry the most logic and are the most likely to silently rot as
jobs.ac.uk's site markup drifts. The HTML fixture below mirrors the real
search-result card structure (`.j-search-result__result`).
"""

from datetime import date

from scraper.parser import (
    extract_job_id,
    parse_listing_html,
    parse_salary,
    _infer_listing_date,
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


class TestInferListingDate:
    REF = date(2026, 6, 9)  # a Tuesday in June

    def test_placed_date_uses_current_year(self):
        # "Date placed" on/before today -> this year
        assert _infer_listing_date("09 Jun", self.REF, "past") == "2026-06-09"

    def test_placed_date_in_future_rolls_back(self):
        # A placed date that lands in the future must be last year
        assert _infer_listing_date("15 Dec", self.REF, "past") == "2025-12-15"

    def test_closing_date_uses_current_year(self):
        assert _infer_listing_date("30 Jun", self.REF, "future") == "2026-06-30"

    def test_closing_date_in_past_rolls_forward(self):
        # A closing date that lands in the past must be next year
        assert _infer_listing_date("01 Jan", self.REF, "future") == "2027-01-01"

    def test_full_month_name(self):
        assert _infer_listing_date("3 September", self.REF, "future") == "2026-09-03"

    def test_unparseable_returns_none(self):
        assert _infer_listing_date("soon", self.REF, "future") is None


# A trimmed-down but structurally faithful copy of two real result cards.
_LISTING_HTML = """
<div id="job-listings">
  <div class="j-search-result__result ie-border-left" data-advert-id="1078028">
    <div class="j-search-result__text">
      <a href="/job/DRV582/full-professor-in-law">Full Professor in Law</a>
      <div class="j-search-result__department">Faculty of Law</div>
      <div class="j-search-result__employer"><b>National University of Singapore</b></div>
      <div>Location: Singapore</div>
      <div class="j-search-result__info"><strong>Salary: </strong>Not Specified</div>
      <div><strong>Date Placed: </strong>09 Jun</div>
    </div>
    <div class="j-search-result__date-logos">
      <div class="j-search-result__date">
        <span class="j-search-result__date-span j-search-result__date">Closes</span>
        <span class="j-search-result__date-span j-search-result__date--blue ">30 Jun</span>
      </div>
    </div>
  </div>
  <div class="j-search-result__result ie-border-left" data-advert-id="1078030">
    <div class="j-search-result__text">
      <a href="/job/DRV584/lecturer-in-food-chemistry">Assistant Lecturer in Food Chemistry</a>
      <div class="j-search-result__department">Faculty of Science</div>
      <div class="j-search-result__employer"><b>Atlantic Technological University</b></div>
      <div>Location: Sligo</div>
      <div class="j-search-result__info"><strong>Salary: </strong>£41,377.94 to £55,990.51</div>
      <div><strong>Date Placed: </strong>09 Jun</div>
    </div>
    <div class="j-search-result__date-logos">
      <div class="j-search-result__date">
        <span class="j-search-result__date-span j-search-result__date">Closes</span>
        <span class="j-search-result__date-span j-search-result__date--blue ">25 Jun</span>
      </div>
    </div>
  </div>
</div>
"""


class TestParseListingHTML:
    REF = date(2026, 6, 9)

    def _jobs(self):
        return parse_listing_html(_LISTING_HTML, "academic-or-research", today=self.REF)

    def test_finds_all_cards(self):
        assert len(self._jobs()) == 2

    def test_core_fields(self):
        job = self._jobs()[0]
        assert job["job_id"] == "DRV582"
        assert job["title"] == "Full Professor in Law"
        assert job["institution"] == "National University of Singapore"
        assert job["department"] == "Faculty of Law"
        assert job["location"] == "Singapore"
        assert job["category"] == "academic-or-research"
        assert job["url"] == "https://www.jobs.ac.uk/job/DRV582/full-professor-in-law"

    def test_dates_inferred(self):
        job = self._jobs()[0]
        assert job["date_posted"] == "2026-06-09"
        assert job["closing_date"] == "2026-06-30"

    def test_not_specified_salary_is_none(self):
        job = self._jobs()[0]
        assert job["salary_raw"] is None
        assert job["salary_min"] is None

    def test_salary_range_parsed(self):
        job = self._jobs()[1]
        assert job["salary_min"] == 41377.0
        assert job["salary_max"] == 55990.0

    def test_enrichment_only_fields_are_none(self):
        # contract_type / hours / region aren't in the listing
        job = self._jobs()[0]
        assert job["contract_type"] is None
        assert job["hours"] is None
        assert job["region"] is None

    def test_empty_html(self):
        assert parse_listing_html("", "technical") == []
