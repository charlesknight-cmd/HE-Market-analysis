"""Regression tests for the dashboard chart builders (geo map in particular)."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard import charts
from dashboard.charts import _ring_signed_area, _uk_geojson, region_choropleth


def test_uk_geojson_winding_matches_plotly_convention():
    """Plotly geo traces need exterior rings clockwise (d3-geo), not RFC 7946 CCW.

    A wrong-wound ring renders as the whole globe minus the shape, which blanked
    the UK map entirely (June 2026).
    """
    gj = _uk_geojson()
    assert gj["features"], "geojson should have features"
    for feat in gj["features"]:
        name = feat["properties"]["name"]
        for polygon in feat["geometry"]["coordinates"]:
            for i, ring in enumerate(polygon):
                ccw = _ring_signed_area(ring) > 0
                if i == 0:
                    assert not ccw, f"{name}: exterior ring must be clockwise"
                else:
                    assert ccw, f"{name}: hole ring must be counterclockwise"


def test_choropleth_pads_missing_nations_to_zero():
    rows = [
        {"region": "England", "job_count": 80},
        {"region": "Scotland", "job_count": 9},
        {"region": "International", "job_count": 11},  # excluded from the map
    ]
    fig = region_choropleth(rows)
    trace = fig.data[0]
    assert sorted(trace.locations) == sorted(charts._UK_NATIONS)
    by_nation = dict(zip(trace.locations, trace.z))
    assert by_nation["England"] == 80
    assert by_nation["Wales"] == 0
    assert by_nation["Northern Ireland"] == 0
    assert "International" not in by_nation


def test_choropleth_placeholder_when_no_uk_rows():
    fig = region_choropleth([{"region": "International", "job_count": 5}])
    assert len(fig.data) == 0
    assert any("location data" in (a.text or "") for a in fig.layout.annotations)


def test_uk_geojson_cache_reuses_until_file_changes():
    """Cache is keyed on mtime: unchanged file → same object; edit → reload."""
    first = _uk_geojson()
    assert _uk_geojson() is first, "unchanged file should reuse the cached object"

    original = charts._GEOJSON_PATH.stat().st_mtime
    try:
        os.utime(charts._GEOJSON_PATH, (original + 5, original + 5))
        assert _uk_geojson() is not first, "mtime change should trigger a reload"
    finally:
        os.utime(charts._GEOJSON_PATH, (original, original))
