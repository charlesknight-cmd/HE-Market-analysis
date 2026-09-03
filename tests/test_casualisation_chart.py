"""Tests for scripts/casualisation_chart.py — the data side (no matplotlib needed)."""

import pytest

import db.schema as schema
from db.queries import bulk_upsert, set_disciplines
from scripts.casualisation_chart import load_data, mix_label, role_flags


class TestMixLabel:
    @pytest.mark.parametrize("ratio,expected", [
        (6.2, "research"), (1.3, "research"),
        (1.25, "balanced"), (1.03, "balanced"), (1.0, "balanced"), (0.8, "balanced"),
        (0.79, "teaching"), (0.15, "teaching"), (0.0, "teaching"), (None, "teaching"),
    ])
    def test_bands(self, ratio, expected):
        assert mix_label(ratio) == expected


class TestRoleFlags:
    @pytest.mark.parametrize("title,expected", [
        ("Research Associate in Machine Learning", (True, False)),
        ("Postdoctoral Research Fellow", (True, False)),
        ("Lecturer in Law", (False, True)),
        ("Senior Lecturer / Associate Professor", (False, True)),
        ("Research Assistant / Lecturer", (True, True)),
        ("Professor of Chemistry", (False, False)),
        ("Head of Research Operations", (False, False)),   # 'research' alone is not a research post
        (None, (False, False)),
    ])
    def test_flags(self, title, expected):
        assert role_flags(title) == expected


def _job(job_id, category, title, contract):
    return {"job_id": job_id, "title": title, "institution": "Uni", "department": None,
            "salary_raw": None, "salary_min": None, "salary_max": None, "closing_date": "2026-12-01",
            "contract_type": contract, "hours": "full-time", "category": category,
            "url": f"https://www.jobs.ac.uk/job/{job_id}/x", "date_posted": "2026-08-01"}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "jobs.db"
    monkeypatch.setattr(schema, "DB_PATH", path)
    schema.init_db()
    return path


def test_load_data_counts_multi_discipline_jobs_under_each(db):
    bulk_upsert([
        _job("B1", "biological-sciences", "Research Associate", "fixed-term"),
        _job("B2", "biological-sciences", "Research Fellow", "fixed-term"),
        _job("B3", "biological-sciences", "Lecturer in Biology", "permanent"),
        _job("L1", "law", "Lecturer in Law", "permanent"),
        _job("L2", "law", "Lecturer in Law", "permanent"),
        _job("L3", "law", "Research Assistant", "fixed-term"),
        _job("L4", "law", "Reader in Law", None),               # no contract type -> excluded from share
        _job("P1", "professional-or-managerial", "Finance Manager", "permanent"),   # legacy slug -> dropped
    ])
    # B1 is also tagged law: it must count under both disciplines
    set_disciplines("B1", [{"facet": "academic", "slug": "biological-sciences", "position": 0},
                           {"facet": "academic", "slug": "law", "position": 1}])
    data = load_data(db, min_n=1)

    by_cat = {r["category"]: r for r in data["rows"]}
    assert set(by_cat) == {"biological-sciences", "law"}
    bio, law = by_cat["biological-sciences"], by_cat["law"]
    assert (bio["n_contract"], bio["fixed"], bio["fixed_pct"]) == (3, 2, 66.7)
    assert (bio["research"], bio["lecturer"], bio["res_per_lec"]) == (2, 1, 2.0)
    assert (law["n_contract"], law["fixed"], law["fixed_pct"]) == (4, 2, 50.0)   # L1 L2 L3 + B1
    assert (law["research"], law["lecturer"], law["res_per_lec"]) == (2, 2, 1.0)
    assert [r["category"] for r in data["rows"]] == ["law", "biological-sciences"]   # ascending fixed_pct

    # Baseline counts jobs once, ignoring the missing contract type
    assert data["meta"]["jobs"] == 8
    assert data["meta"]["contracted"] == 7
    assert data["meta"]["fixed_pct_all"] == 42.9                                     # 3 of 7
    assert data["meta"]["posted_min"] == "2026-08-01"


def test_sample_gate_and_missing_lecturers(db):
    bulk_upsert([_job("E1", "economics", "Research Fellow", "fixed-term"),
                 _job("E2", "economics", "Research Fellow", "fixed-term")])
    assert load_data(db, min_n=3)["rows"] == []
    row = load_data(db, min_n=1)["rows"][0]
    assert row["res_per_lec"] is None       # no lecturer posts: ratio undefined, not a division error
