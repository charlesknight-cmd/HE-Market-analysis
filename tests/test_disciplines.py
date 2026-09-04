"""Tests for multi-discipline attribution.

Covers the detail-page Subject Area(s) parser and the expired-job redirect
recovery in scraper/detail.py, plus the job_disciplines table, the
jobs_by_discipline / jobs_primary_discipline views and the query helpers in
db/queries.py, exercised against a throwaway SQLite file.
"""

import sqlite3
from datetime import date, timedelta

import pytest

import db.schema as schema
from db.queries import (
    bulk_upsert,
    discipline_coverage,
    get_all_jobs,
    jobs_needing_disciplines,
    set_disciplines,
    update_enrichment,
)
from scraper.detail import (
    enrich_url,
    is_expired_redirect,
    parse_redirect_disciplines,
    parse_subject_areas,
)


# --------------------------------------------------------------- fixtures --

def _form(*inputs: str) -> str:
    body = "".join(f'<input {i}>' for i in inputs)
    return f'<form method="GET" action="/search/"><div class="j-form-input">{body}</div></form>'


def _page(*forms: str, tail: str = '<div><p><b>Location(s):</b></p><input type="button" value="London"></div>') -> str:
    return ('<html><body><div><p><b>Subject Area(s):</b></p>'
            + "".join(forms) + '</div>' + tail + '</body></html>')


# Mirrors the real sidebar markup for a job tagged with one academic discipline,
# two of its sub-disciplines and one non-academic discipline (DSU150).
_MIXED_PAGE = _page(
    _form('name="academicDisciplineFacet[0]" value="social-sciences-and-social-care" type="hidden"',
          'class="parent-category" type="submit" value="Social Sciences &amp; Social Care"'),
    _form('name="academicDisciplineFacet[0]" value="social-sciences-and-social-care" type="hidden"',
          'name="subDisciplineFacet[0]" value="social-policy" type="hidden"',
          'class="" type="submit" value="Social Policy"'),
    _form('name="academicDisciplineFacet[0]" value="social-sciences-and-social-care" type="hidden"',
          'name="subDisciplineFacet[0]" value="other-social-sciences" type="hidden"',
          'class="" type="submit" value="Other Social Sciences"'),
    _form('name="nonAcademicDisciplineFacet[0]" value="student-services" type="hidden"',
          'class="parent-category" type="submit" value="Student Services"'),
)

# Two academic disciplines, no subs (DSL337).
_TWO_ACADEMIC_PAGE = _page(
    _form('name="academicDisciplineFacet[0]" value="economics" type="hidden"',
          'class="parent-category" type="submit" value="Economics"'),
    _form('name="academicDisciplineFacet[0]" value="politics-and-government" type="hidden"',
          'class="parent-category" type="submit" value="Politics &amp; Government"'),
)

_REDIRECT_URL = (
    "https://www.jobs.ac.uk/search/?academicDisciplineFacet[0]=engineering-and-technology"
    "&subDisciplineFacet[0]=electrical-and-electronic-engineering"
    "&nonAcademicDisciplineFacet[0]=laboratory-clinical-and-technician"
    "&salaryBandFacet[0]=30000-39999&salaryBandFacet[1]=25000-29999&expired-job-redirect=true"
)


# ---------------------------------------------------- parse_subject_areas --

class TestParseSubjectAreas:
    def test_mixed_tags_with_names_parents_and_positions(self):
        tags = parse_subject_areas(_MIXED_PAGE)
        assert [(t["facet"], t["slug"], t["name"], t["parent_slug"], t["position"]) for t in tags] == [
            ("academic", "social-sciences-and-social-care", "Social Sciences & Social Care", None, 0),
            ("sub", "social-policy", "Social Policy", "social-sciences-and-social-care", 0),
            ("sub", "other-social-sciences", "Other Social Sciences", "social-sciences-and-social-care", 1),
            ("non-academic", "student-services", "Student Services", None, 0),
        ]

    def test_two_academic_disciplines_keep_page_order(self):
        tags = parse_subject_areas(_TWO_ACADEMIC_PAGE)
        assert [(t["slug"], t["position"]) for t in tags] == [
            ("economics", 0), ("politics-and-government", 1)]
        assert all(t["facet"] == "academic" for t in tags)
        assert tags[1]["name"] == "Politics & Government"   # entity unescaped

    def test_forms_after_the_block_are_ignored(self):
        # The Job tools sidebar that follows also contains <form> elements.
        html = _TWO_ACADEMIC_PAGE.replace(
            "</body>",
            '<div><h5>Job tools</h5><form id="saveSearchAsJobAlertCTA">'
            '<input name="academicDisciplineFacet[0]" value="law" type="hidden"></form></div></body>')
        assert [t["slug"] for t in parse_subject_areas(html)] == ["economics", "politics-and-government"]

    def test_duplicate_tag_collapsed(self):
        html = _page(
            _form('name="academicDisciplineFacet[0]" value="law" type="hidden"', 'type="submit" value="Law"'),
            _form('name="academicDisciplineFacet[0]" value="law" type="hidden"', 'type="submit" value="Law"'),
        )
        assert len(parse_subject_areas(html)) == 1

    def test_attribute_order_and_single_quotes_tolerated(self):
        html = _page(_form("type='hidden' value='psychology' name='academicDisciplineFacet[]'",
                           "value='Psychology' type='submit'"))
        assert parse_subject_areas(html) == [
            {"facet": "academic", "slug": "psychology", "name": "Psychology", "parent_slug": None, "position": 0}]

    def test_no_block_returns_empty(self):
        assert parse_subject_areas("<html><body>nothing here</body></html>") == []
        assert parse_subject_areas("") == []


# ------------------------------------------------------ redirect recovery --

class TestRedirect:
    def test_detects_expired_redirect(self):
        assert is_expired_redirect(_REDIRECT_URL)
        assert is_expired_redirect("https://www.jobs.ac.uk/search/?academicDisciplineFacet[0]=law")
        assert not is_expired_redirect("https://www.jobs.ac.uk/job/DSL337/full-professor")
        assert not is_expired_redirect(None)

    def test_parses_facets_and_links_sub_to_sole_parent(self):
        tags = parse_redirect_disciplines(_REDIRECT_URL)
        assert [(t["facet"], t["slug"], t["parent_slug"], t["position"]) for t in tags] == [
            ("academic", "engineering-and-technology", None, 0),
            ("sub", "electrical-and-electronic-engineering", "engineering-and-technology", 0),
            ("non-academic", "laboratory-clinical-and-technician", None, 0),
        ]
        assert all(t["name"] is None for t in tags)

    def test_sub_parent_unknown_with_several_academics(self):
        url = ("https://www.jobs.ac.uk/search/?academicDisciplineFacet[0]=law"
               "&academicDisciplineFacet[1]=economics&subDisciplineFacet[0]=criminal-law")
        tags = parse_redirect_disciplines(url)
        assert [t["slug"] for t in tags] == ["law", "economics", "criminal-law"]
        assert tags[2]["parent_slug"] is None

    def test_repeated_index_still_yields_both(self):
        # Seen in the wild: two non-academic facets both indexed [0].
        url = ("https://www.jobs.ac.uk/search/?nonAcademicDisciplineFacet[0]=human-resources"
               "&nonAcademicDisciplineFacet[0]=pr-marketing&expired-job-redirect=true")
        assert [t["slug"] for t in parse_redirect_disciplines(url)] == ["human-resources", "pr-marketing"]


class _FakeResponse:
    def __init__(self, text, url):
        self.text, self.url = text, url

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, text, final_url):
        self._resp = _FakeResponse(text, final_url)

    def get(self, url, **kwargs):
        return self._resp


class TestEnrichUrl:
    def test_live_page_carries_disciplines(self):
        data = enrich_url("https://www.jobs.ac.uk/job/X/y",
                          session=_FakeSession(_TWO_ACADEMIC_PAGE, "https://www.jobs.ac.uk/job/X/y"))
        assert data["discipline_source"] == "detail"
        assert data["expired"] is False
        assert [t["slug"] for t in data["disciplines"]] == ["economics", "politics-and-government"]
        assert data["closing_date"] is None   # no JSON-LD in the fixture, other fields still present

    def test_expired_redirect_recovers_disciplines_only(self):
        data = enrich_url("https://www.jobs.ac.uk/job/X/y",
                          session=_FakeSession("<html>search results</html>", _REDIRECT_URL))
        assert data["expired"] is True
        assert data["discipline_source"] == "redirect"
        assert [t["slug"] for t in data["disciplines"] if t["facet"] == "academic"] == ["engineering-and-technology"]
        assert data["closing_date"] is None and data["salary_min"] is None


# ------------------------------------------------------------- DB layer --

# Any day seven days back lies in the previous, COMPLETE ISO week — the weekly
# series exclude the current partial week, so windowed tests post there.
LAST_WEEK = (date.today() - timedelta(days=7)).isoformat()


def _job(job_id, category, **extra):
    return {"job_id": job_id, "title": f"Lecturer {job_id}", "institution": "Uni",
            "department": None, "salary_raw": None, "salary_min": 40000.0, "salary_max": 45000.0,
            "closing_date": "2026-12-01", "contract_type": "permanent", "hours": "full-time",
            "category": category, "url": f"https://www.jobs.ac.uk/job/{job_id}/x",
            "date_posted": LAST_WEEK, **extra}


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "jobs.db"
    monkeypatch.setattr(schema, "DB_PATH", path)
    schema.init_db()
    return path


def _rows(path, sql):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


class TestDisciplineStorage:
    def test_listing_scans_accrue_every_facet(self, tmp_db):
        # Same job surfaces under two discipline scans; a second job under one.
        bulk_upsert([_job("A1", "economics"), _job("B1", "law")])
        bulk_upsert([_job("A1", "politics-and-government")])

        assert _rows(tmp_db, "SELECT category FROM jobs WHERE job_id='A1'") == [("economics",)]
        assert _rows(tmp_db, "SELECT slug, source FROM job_disciplines WHERE job_id='A1' ORDER BY slug") == [
            ("economics", "listing"), ("politics-and-government", "listing")]
        # View: A1 counts under both, B1 under one -> 3 rows
        assert _rows(tmp_db, "SELECT job_id, category FROM jobs_by_discipline ORDER BY job_id, category") == [
            ("A1", "economics"), ("A1", "politics-and-government"), ("B1", "law")]
        assert _rows(tmp_db, "SELECT COUNT(*) FROM jobs_primary_discipline") == [(2,)]

    def test_legacy_job_type_slug_is_not_a_discipline_but_view_falls_back(self, tmp_db):
        bulk_upsert([_job("L1", "academic-or-research")])
        assert _rows(tmp_db, "SELECT COUNT(*) FROM job_disciplines") == [(0,)]
        assert _rows(tmp_db, "SELECT category, position FROM jobs_by_discipline") == [("academic-or-research", None)]
        assert _rows(tmp_db, "SELECT category FROM jobs_primary_discipline") == [("academic-or-research",)]

    def test_detail_tags_upgrade_source_and_set_primary(self, tmp_db):
        bulk_upsert([_job("A1", "economics")])
        set_disciplines("A1", [
            {"facet": "academic", "slug": "politics-and-government", "name": "Politics & Government", "position": 0},
            {"facet": "academic", "slug": "economics", "name": "Economics", "position": 1},
            {"facet": "sub", "slug": "macroeconomics", "name": "Macroeconomics",
             "parent_slug": "economics", "position": 0},
        ])
        rows = _rows(tmp_db, "SELECT facet, slug, source, position, parent_slug FROM job_disciplines "
                             "WHERE job_id='A1' ORDER BY facet, position")
        assert rows == [
            ("academic", "politics-and-government", "detail", 0, None),
            ("academic", "economics", "detail", 1, None),
            ("sub", "macroeconomics", "detail", 0, "economics"),
        ]
        # Primary = first-listed on the detail page, not the facet scraped first
        assert _rows(tmp_db, "SELECT category FROM jobs_primary_discipline") == [("politics-and-government",)]
        assert _rows(tmp_db, "SELECT category FROM jobs WHERE job_id='A1'") == [("economics",)]  # untouched
        assert _rows(tmp_db, "SELECT disciplines_at IS NOT NULL FROM jobs WHERE job_id='A1'") == [(1,)]
        # Sub-disciplines never leak into the academic-discipline view
        assert _rows(tmp_db, "SELECT COUNT(*) FROM jobs_by_discipline WHERE job_id='A1'") == [(2,)]

    def test_later_listing_scan_cannot_downgrade_detail_source(self, tmp_db):
        bulk_upsert([_job("A1", "economics")])
        set_disciplines("A1", [{"facet": "academic", "slug": "economics", "name": "Economics", "position": 0}])
        bulk_upsert([_job("A1", "economics")])
        assert _rows(tmp_db, "SELECT source, position FROM job_disciplines WHERE job_id='A1'") == [("detail", 0)]

    def test_redirect_source_sits_between_listing_and_detail(self, tmp_db):
        bulk_upsert([_job("A1", "economics")])
        set_disciplines("A1", [{"facet": "academic", "slug": "economics", "position": 0}], source="redirect")
        assert _rows(tmp_db, "SELECT source, name FROM job_disciplines WHERE job_id='A1'") == [("redirect", "Economics")]
        set_disciplines("A1", [{"facet": "academic", "slug": "economics", "name": "Economics", "position": 0}])
        assert _rows(tmp_db, "SELECT source FROM job_disciplines WHERE job_id='A1'") == [("detail",)]

    def test_update_enrichment_writes_disciplines_and_stamps(self, tmp_db):
        bulk_upsert([_job("A1", "economics")])
        update_enrichment("A1", {"closing_date": "2026-12-31",
                                 "disciplines": [{"facet": "academic", "slug": "law", "name": "Law", "position": 0}],
                                 "discipline_source": "detail"})
        assert _rows(tmp_db, "SELECT closing_date, disciplines_at IS NOT NULL, enriched_at IS NOT NULL "
                             "FROM jobs WHERE job_id='A1'") == [("2026-12-31", 1, 1)]
        assert sorted(r[0] for r in _rows(tmp_db, "SELECT slug FROM job_disciplines WHERE job_id='A1'")) == [
            "economics", "law"]

    def test_update_enrichment_without_disciplines_leaves_stamp_null(self, tmp_db):
        bulk_upsert([_job("A1", "economics")])
        update_enrichment("A1", {"closing_date": "2026-12-31"})
        assert _rows(tmp_db, "SELECT disciplines_at FROM jobs WHERE job_id='A1'") == [(None,)]

    def test_empty_detail_page_still_stamps(self, tmp_db):
        bulk_upsert([_job("A1", "economics")])
        set_disciplines("A1", [])
        assert jobs_needing_disciplines() == []

    def test_pending_order_and_coverage(self, tmp_db):
        bulk_upsert([_job("OLD", "law", closing_date="2026-01-01"),
                     _job("LIVE", "law", closing_date="2026-12-01"),
                     _job("MID", "law", closing_date="2026-06-01")])
        assert [j["job_id"] for j in jobs_needing_disciplines()] == ["LIVE", "MID", "OLD"]
        assert [j["job_id"] for j in jobs_needing_disciplines(limit=1)] == ["LIVE"]
        set_disciplines("LIVE", [{"facet": "academic", "slug": "law", "position": 0},
                                 {"facet": "academic", "slug": "economics", "position": 1}])
        cov = discipline_coverage()
        assert cov["total_jobs"] == 3 and cov["stamped"] == 1 and cov["pending"] == 2
        assert cov["jobs_by_source"] == {"detail": 1, "listing": 2}
        assert cov["multi_discipline_jobs"] == 1

    def test_get_all_jobs_exposes_disciplines_in_order(self, tmp_db):
        bulk_upsert([_job("A1", "economics"), _job("L1", "academic-or-research")])
        set_disciplines("A1", [{"facet": "academic", "slug": "politics-and-government", "position": 0},
                               {"facet": "academic", "slug": "economics", "position": 1}])
        by_id = {j["job_id"]: j["disciplines"] for j in get_all_jobs()}
        assert by_id == {"A1": "politics-and-government,economics", "L1": "academic-or-research"}


class TestAnalysisUsesViews:
    def test_weekly_counts_count_each_discipline(self, tmp_db):
        from analysis.trends import category_weekly_counts, headline_stats
        bulk_upsert([_job("A1", "economics")])
        bulk_upsert([_job("A1", "law")])
        counts = {r["category"]: r["job_count"] for r in category_weekly_counts(weeks=4)}
        assert counts == {"economics": 1, "law": 1}
        assert headline_stats()["disciplines"] == 2

    def test_spike_candidates_count_jobs_not_tags(self, tmp_db):
        from analysis.institutions import spike_candidates
        bulk_upsert([_job("A1", "economics"), _job("A2", "economics"), _job("A3", "law")])
        bulk_upsert([_job("A1", "law")])
        rows = spike_candidates(days=7, threshold=3)
        assert len(rows) == 1
        assert rows[0]["job_count"] == 3
        assert set(rows[0]["category_list"].split(",")) == {"economics", "law"}
