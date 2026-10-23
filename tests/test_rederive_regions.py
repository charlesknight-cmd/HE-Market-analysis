"""Tests for scripts/rederive_regions.py against a throwaway SQLite file.

The page fetch is stubbed, so these cover the selection, institution-consensus
fallback, dry-run and write rules, not the parser (see test_detail.py).
"""

import sqlite3

import pytest

import db.schema as schema
import scripts.rederive_regions as rr

_EMPTY = {"closing_date": None, "contract_type": None, "hours": None, "location": None,
          "region": None, "date_posted": None, "salary_min": None, "salary_max": None,
          "disciplines": [], "discipline_source": "detail", "expired": False}


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "jobs.db"
    monkeypatch.setattr(schema, "DB_PATH", path)
    schema.init_db()
    rows = [
        # job_id, institution, region, contract_type, date_posted
        ("X1", "XJTLU", None, None, "2026-08-01"),        # live enhanced page
        ("X2", "XJTLU", None, None, "2026-06-01"),        # expired -> consensus
        ("X3", "XJTLU", "International", None, "2026-08-02"),
        ("U1", "UWS", None, None, "2026-08-01"),          # expired, 1 sibling only
        ("U2", "UWS", "Scotland", None, "2026-08-01"),
        ("D1", "DTU", "England", "fixed-term", "2026-08-13"),  # wrong mixed-location pick
        ("K1", "Keele", "England", None, "2026-08-01"),   # not a target
    ]
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO jobs (job_id, title, institution, region, contract_type, date_posted, "
        "url, first_seen, last_seen) VALUES (?, 't', ?, ?, ?, ?, ?, '2026-08-01', '2026-08-01')",
        [(j, i, r, c, d, f"https://www.jobs.ac.uk/job/{j}/x") for j, i, r, c, d in rows])
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def pages(monkeypatch):
    responses = {
        "X1": {**_EMPTY, "region": "International", "location": "Suzhou",
               "contract_type": "fixed-term", "hours": "full-time"},
        "X2": {**_EMPTY, "expired": True},
        "U1": {**_EMPTY, "expired": True},
        "D1": {**_EMPTY, "region": "International", "location": "Lyngby",
               "contract_type": "permanent"},
    }
    monkeypatch.setattr(rr, "enrich_url",
                        lambda url, session=None: responses.get(url.split("/")[4]))


def _state(path):
    conn = sqlite3.connect(path)
    try:
        return {r[0]: r[1:] for r in conn.execute(
            "SELECT job_id, region, contract_type, hours FROM jobs")}
    finally:
        conn.close()


def test_dry_run_writes_nothing(tmp_db, pages):
    before = _state(tmp_db)
    summary = rr.rederive_regions(["D1"], delay=0, apply=False)
    assert _state(tmp_db) == before
    assert summary["via page"] == 2
    assert summary["via institution"] == 1
    assert summary["unresolved"] == 1


def test_apply(tmp_db, pages):
    summary = rr.rederive_regions(["D1"], delay=0, apply=True)
    state = _state(tmp_db)
    assert state["X1"] == ("International", "fixed-term", "full-time")
    assert state["X2"] == ("International", None, None)      # XJTLU consensus
    assert state["U1"] == (None, None, None)                 # one sibling isn't enough
    assert state["D1"] == ("International", "fixed-term", None)  # contract never overwritten
    assert state["K1"] == ("England", None, None)
    assert summary["-> International"] == 3
    assert summary["in 2026-07-23..2026-10-22 window"] == 2
