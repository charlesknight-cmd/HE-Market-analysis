"""Unit tests for the pure URL-building logic in scraper/fetcher.py.

Each page request carries the discipline in the `academicDisciplineFacet[]`
query param (URL-encoded), making it self-describing and stateless — these tests
pin that scheme down.
"""

from config import SEARCH_BASE
from scraper.fetcher import _page_url


class TestPageUrl:
    def test_includes_encoded_facet_and_discipline(self):
        url = _page_url("computer-sciences", start_index=1, page_size=25)
        assert url == (
            f"{SEARCH_BASE}/?academicDisciplineFacet%5B%5D=computer-sciences"
            "&sortOrder=1&pageSize=25&startIndex=1"
        )

    def test_brackets_are_percent_encoded(self):
        # Raw [] in a query key trips up some clients — must be %5B%5D
        url = _page_url("law", 1, 25)
        assert "academicDisciplineFacet%5B%5D=law" in url
        assert "[]" not in url

    def test_start_index_advances(self):
        assert "startIndex=26" in _page_url("law", 26, 25)
        assert "startIndex=51" in _page_url("law", 51, 25)

    def test_page_size_in_url(self):
        assert "pageSize=25" in _page_url("psychology", 1, 25)

    def test_facet_present_on_every_page(self):
        # The facet must ride on page 2+ too, not just page 1
        assert "academicDisciplineFacet%5B%5D=psychology" in _page_url("psychology", 26, 25)
