"""Regression tests for the dashboard chart builders (geo map in particular)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard import charts
from dashboard.charts import _uk_geojson, _uk_map_view, region_choropleth


def test_map_uses_winding_insensitive_trace():
    """The map must use the MapLibre ``choroplethmap`` trace, not the geo
    ``choropleth`` trace.

    The geo trace renders on a sphere (d3-geo): a polygon wound the "wrong" way
    for whatever Plotly.js version is in play inverts to fill the whole frame —
    the recurring "blank square". MapLibre projects on a plane and is immune to
    ring winding, so we lock the trace type in to stop a regression back to the
    fragile, version-sensitive approach.
    """
    fig = region_choropleth([{"region": "England", "job_count": 5}])
    assert fig.data[0].type == "choroplethmap"
    assert fig.layout.map.style == "white-bg"


def test_uk_map_view_frames_the_uk():
    """Centre/zoom derived from the geojson should actually sit over the UK."""
    center, zoom = _uk_map_view(_uk_geojson())
    assert 50 <= center["lat"] <= 58, center
    assert -6 <= center["lon"] <= -1, center
    assert 2.5 <= zoom <= 5.5, zoom


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


def test_salary_scatter_labels_only_standouts():
    """Regression: labelling every institution turned the scatter into an
    unreadable smear. Now everyone is plotted and hoverable, but only a handful
    of standouts carry a text label.
    """
    rows = [{"institution": f"Institution number {i}",
             "job_count": (i % 5) + 1,
             "avg_salary_min": 30000 + i * 700,
             "avg_salary_max": 40000 + i * 700} for i in range(18)]
    fig = charts.institution_salary_scatter(rows)
    markers, labels = fig.data[0], fig.data[1]
    assert markers.mode == "markers"
    assert len(markers.x) == 18, "every institution should be plotted"
    n_labels = len([t for t in labels.text if t])
    assert 0 < n_labels < 18, "only some institutions should be labelled"
    assert n_labels <= 8


def test_salary_scatter_placeholder_when_empty():
    fig = charts.institution_salary_scatter([])
    assert len(fig.data) == 0
