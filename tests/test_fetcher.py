"""Unit tests for the pure URL-building logic in scraper/fetcher.py.

The pagination scheme is subtle: page 1 uses the pretty `/search/<category>`
path (which sets the category in the server-side session), while later pages
must hit the bare `/search/?startIndex=` endpoint and rely on the session
cookie to stay in the category. These tests pin that behaviour down.
"""

from config import SEARCH_BASE
from scraper.fetcher import _page_url

BASE = f"{SEARCH_BASE}/academic-or-research"


class TestPageUrl:
    def test_first_page_uses_category_path(self):
        url = _page_url(BASE, start_index=1, page_size=25)
        assert url == f"{BASE}?sortOrder=1&pageSize=25&startIndex=1"

    def test_start_index_zero_or_less_treated_as_first_page(self):
        assert _page_url(BASE, 0, 25).startswith(BASE + "?")

    def test_later_pages_drop_the_category_path(self):
        url = _page_url(BASE, start_index=26, page_size=25)
        # Category is no longer in the path — it rides on the session cookie.
        assert url == f"{SEARCH_BASE}/?sortOrder=1&pageSize=25&startIndex=26"
        assert "academic-or-research" not in url

    def test_page_size_is_honoured_in_url(self):
        assert "pageSize=25" in _page_url(BASE, 51, 25)
