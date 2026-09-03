"""Tests for scripts/attribution_chart.py — the data side (no matplotlib needed)."""

import pytest

import db.schema as schema
from db.queries import bulk_upsert, set_disciplines
from scripts.attribution_chart import load_data


def _job(job_id, category):
    return {"job_id": job_id, "title": f"Post {job_id}", "institution": "Uni", "department": None,
            "salary_raw": None, "salary_min": None, "salary_max": None, "closing_date": "2027-01-01",
            "contract_type": "permanent", "hours": "full-time", "category": category,
            "url": f"https://www.jobs.ac.uk/job/{job_id}/x", "date_posted": "2026-08-01"}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "jobs.db"
    monkeypatch.setattr(schema, "DB_PATH", path)
    schema.init_db()
    return path


def test_three_attribution_rules_and_meta(db):
    bulk_upsert([_job("A", "law"), _job("B", "law"), _job("C", "economics"),
                 _job("L", "professional-or-managerial")])          # legacy slug: dropped from rows
    # A: page lists economics first, then law  -> first-listed economics, every-tag both
    set_disciplines("A", [{"facet": "academic", "slug": "economics", "position": 0},
                          {"facet": "academic", "slug": "law", "position": 1}])
    # B: law only. C: only the listing-scan tag (economics) that bulk_upsert records.
    # L: legacy slug, so the listing scan records no tag at all.
    set_disciplines("B", [{"facet": "academic", "slug": "law", "position": 0}])

    data = load_data(db)
    by = {r["category"]: r for r in data["rows"]}
    assert set(by) == {"law", "economics"}
    assert (by["law"]["every_tag"], by["law"]["first_listed"], by["law"]["first_scanned"]) == (2, 1, 2)
    assert (by["economics"]["every_tag"], by["economics"]["first_listed"], by["economics"]["first_scanned"]) == (2, 2, 1)
    assert by["law"]["ratio"] == 2.0 and by["economics"]["ratio"] == 1.0
    assert [r["category"] for r in data["rows"]] == ["economics", "law"]        # ascending ratio

    m = data["meta"]
    assert m["adverts"] == 4 and m["tags"] == 4                               # A:2, B:1, C:1, L:0
    assert m["tags_per_advert"] == 1.0
    assert m["multi_pct"] == 25.0                                             # only A has 2+ tags
    assert m["tag_histogram"] == [(0, 1), (1, 2), (2, 1)]
    assert m["posted_min"] == "2026-08-01"


def test_ratio_none_when_never_first_listed(db):
    bulk_upsert([_job("A", "law")])
    set_disciplines("A", [{"facet": "academic", "slug": "economics", "position": 0},
                          {"facet": "academic", "slug": "law", "position": 1}])
    data = load_data(db)
    by = {r["category"]: r for r in data["rows"]}
    assert by["law"]["first_listed"] == 0 and by["law"]["ratio"] is None
    assert data["rows"][-1]["category"] == "law"                            # None sorts last
