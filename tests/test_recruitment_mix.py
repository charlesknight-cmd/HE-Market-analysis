"""Tests for the recruitment-mix query and the precarity_mix_bar chart."""

from datetime import date

import pytest

import db.schema as schema
from analysis.trends import mix_label, recruitment_mix_by_discipline, role_flags
from dashboard import charts
from db.queries import bulk_upsert, set_disciplines

TODAY = date.today().isoformat()


class TestClassifiers:
    @pytest.mark.parametrize("ratio,expected", [
        (6.2, "research"), (1.3, "research"), (float("inf"), "research"),
        (1.25, "balanced"), (1.03, "balanced"), (1.0, "balanced"), (0.8, "balanced"),
        (0.79, "teaching"), (0.15, "teaching"), (0.0, "teaching"), (None, "teaching"),
    ])
    def test_mix_bands(self, ratio, expected):
        assert mix_label(ratio) == expected

    @pytest.mark.parametrize("title,expected", [
        ("Research Associate in Machine Learning", (True, False)),
        ("Postdoctoral Research Fellow", (True, False)),
        ("Lecturer in Law", (False, True)),
        ("Senior Lecturer / Associate Professor", (False, True)),
        ("Research Assistant / Lecturer", (True, True)),
        ("Professor of Chemistry", (False, False)),
        ("Head of Research Operations", (False, False)),
        (None, (False, False)),
    ])
    def test_role_flags(self, title, expected):
        assert role_flags(title) == expected


def _job(job_id, category, title, contract):
    return {"job_id": job_id, "title": title, "institution": "Uni", "department": None,
            "salary_raw": None, "salary_min": None, "salary_max": None, "closing_date": "2027-01-01",
            "contract_type": contract, "hours": "full-time", "category": category,
            "url": f"https://www.jobs.ac.uk/job/{job_id}/x", "date_posted": TODAY}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "jobs.db"
    monkeypatch.setattr(schema, "DB_PATH", path)
    schema.init_db()
    return path


class TestRecruitmentMixQuery:
    def test_counts_mix_and_market_baseline(self, db):
        bulk_upsert([
            _job("B1", "biological-sciences", "Research Associate", "fixed-term"),
            _job("B2", "biological-sciences", "Research Fellow", "fixed-term"),
            _job("B3", "biological-sciences", "Lecturer in Biology", "permanent"),
            _job("L1", "law", "Lecturer in Law", "permanent"),
            _job("L2", "law", "Lecturer in Law", "permanent"),
            _job("L3", "law", "Research Assistant", "fixed-term"),
            _job("L4", "law", "Reader in Law", None),                        # no contract: counted for roles only
            _job("P1", "professional-or-managerial", "Finance Manager", "permanent"),   # legacy slug: skipped
        ])
        set_disciplines("B1", [{"facet": "academic", "slug": "biological-sciences", "position": 0},
                               {"facet": "academic", "slug": "law", "position": 1}])    # counts under both
        rows = recruitment_mix_by_discipline(days=30, min_n=1)

        assert [r["category"] for r in rows] == ["law", "biological-sciences"]        # ascending fixed-term %
        law, bio = rows
        assert (law["n"], law["fixed_term"], law["fixed_term_pct"]) == (4, 2, 50.0)   # L1 L2 L3 + B1
        assert (law["research"], law["lecturer"], law["res_per_lec"], law["mix"]) == (2, 2, 1.0, "balanced")
        assert (bio["n"], bio["fixed_term_pct"]) == (3, 66.7)
        assert (bio["research"], bio["lecturer"], bio["res_per_lec"], bio["mix"]) == (2, 1, 2.0, "research")
        # Market baseline counts each job once, ignoring missing contract types: 3 fixed of 7
        assert all(r["market_pct"] == 42.9 for r in rows)

    def test_sample_gate_and_no_lecturer_posts(self, db):
        bulk_upsert([_job("E1", "economics", "Research Fellow", "fixed-term"),
                     _job("E2", "economics", "Research Fellow", "fixed-term")])
        assert recruitment_mix_by_discipline(days=30, min_n=3) == []
        row = recruitment_mix_by_discipline(days=30, min_n=1)[0]
        assert row["res_per_lec"] == float("inf") and row["mix"] == "research"

    def test_window_excludes_old_postings(self, db):
        old = _job("O1", "law", "Lecturer in Law", "permanent"); old["date_posted"] = "2020-01-01"
        bulk_upsert([old])
        assert recruitment_mix_by_discipline(days=30, min_n=1) == []


class TestPrecarityMixBar:
    ROWS = [
        {"category": "business-and-management-studies", "n": 100, "fixed_term": 36, "fixed_term_pct": 36.0,
         "research": 10, "lecturer": 60, "res_per_lec": 0.17, "mix": "teaching", "market_pct": 62.0},
        {"category": "historical-and-philosophical-studies", "n": 100, "fixed_term": 80, "fixed_term_pct": 80.0,
         "research": 30, "lecturer": 30, "res_per_lec": 1.0, "mix": "balanced", "market_pct": 62.0},
        {"category": "biological-sciences", "n": 100, "fixed_term": 83, "fixed_term_pct": 83.0,
         "research": 120, "lecturer": 20, "res_per_lec": 6.0, "mix": "research", "market_pct": 62.0},
    ]

    def test_one_trace_per_mix_band_with_legend_names(self):
        fig = charts.precarity_mix_bar(self.ROWS)
        by_name = {t.name: t for t in fig.data}
        assert set(by_name) == set(charts._MIX_NAMES.values())
        assert all(t.type == "bar" and t.orientation == "h" for t in fig.data)
        research = by_name[charts._MIX_NAMES["research"]]
        assert list(research.y) == ["Biological Sciences"]
        assert list(research.x) == [83.0]
        assert research.marker.color == charts._ACCENT
        assert by_name[charts._MIX_NAMES["balanced"]].marker.color == charts._OTHER_COLOUR
        # ratio rides on hover
        assert research.customdata[0][0] == "6.0"

    def test_ordered_ascending_with_baseline_line(self):
        fig = charts.precarity_mix_bar(self.ROWS)
        assert list(fig.layout.yaxis.categoryarray) == [
            "Business & Management Studies", "Historical & Philosophical Studies", "Biological Sciences"]
        assert fig.layout.barmode == "overlay"
        assert any(s.x0 == 62.0 for s in fig.layout.shapes)
        assert any("62%" in (a.text or "") for a in fig.layout.annotations)

    def test_missing_band_is_simply_absent(self):
        fig = charts.precarity_mix_bar([r for r in self.ROWS if r["mix"] != "balanced"])
        assert len(fig.data) == 2

    def test_placeholder_when_empty(self):
        fig = charts.precarity_mix_bar([])
        assert len(fig.data) == 0
        assert any("data" in (a.text or "").lower() for a in fig.layout.annotations)
