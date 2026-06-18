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


def test_posting_volume_line_reindexes_and_zero_fills():
    """Gaps between posting dates must be filled with 0 on a contiguous daily
    range BEFORE the rolling mean, so quiet days pull the average down rather
    than being skipped over.
    """
    import pandas as pd
    # Two real posting days a week apart -> 6 missing days that must appear as 0.
    rows = [
        {"day": "2026-03-09", "job_count": 10},
        {"day": "2026-03-16", "job_count": 4},
    ]
    fig = charts.posting_volume_line(rows)
    daily = fig.data[0]
    xs = pd.to_datetime(list(daily.x))
    # Contiguous 8-day span (09th..16th inclusive), no gaps.
    assert len(xs) == 8
    assert (xs == pd.date_range("2026-03-09", "2026-03-16", freq="D")).all()
    by_day = dict(zip([d.strftime("%Y-%m-%d") for d in xs], daily.y))
    assert by_day["2026-03-09"] == 10
    assert by_day["2026-03-16"] == 4
    assert by_day["2026-03-12"] == 0, "interior gap day must be zero-filled"
    # Rolling average trace present (len >= 3) and reflects the zero days.
    assert any(t.name == "7-day avg" for t in fig.data)


def test_posting_volume_line_placeholder_when_empty():
    fig = charts.posting_volume_line([])
    assert len(fig.data) == 0
    assert any("data" in (a.text or "").lower() for a in fig.layout.annotations)


def test_weekday_cadence_orders_monday_first_and_pads_weekends():
    """Mon..Sun order, and weekdays missing from the query are padded to zero so
    all seven days render."""
    # Only Tue (2) and Thu (4) present in the data — mirrors the real snapshot
    # where weekends and some weekdays have no postings.
    rows = [{"dow": 2, "job_count": 45}, {"dow": 4, "job_count": 42}]
    fig = charts.weekday_cadence_bar(rows)
    bar = fig.data[0]
    assert list(bar.x) == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    by_day = dict(zip(bar.x, bar.y))
    assert by_day["Tue"] == 45
    assert by_day["Thu"] == 42
    assert by_day["Mon"] == 0  # padded
    assert by_day["Sat"] == 0  # padded weekend
    assert by_day["Sun"] == 0  # padded weekend
    # Zero-weekend note is shown when both weekend days are empty.
    assert any("weekend" in (a.text or "").lower() for a in fig.layout.annotations)


def test_weekday_cadence_empty():
    fig = charts.weekday_cadence_bar([])
    assert len(fig.data) == 0
    assert any("data" in (a.text or "").lower() for a in fig.layout.annotations)


def test_recruiter_concentration_curve_perfect_equality():
    """An even distribution should give Gini ~0 and a curve hugging the 45° line."""
    rows = [{"institution": f"Uni {i}", "job_count": 5} for i in range(10)]
    fig = charts.recruiter_concentration_curve(rows)
    # Two traces: equality reference line + Lorenz curve.
    assert len(fig.data) == 2
    equality, lorenz = fig.data[0], fig.data[1]
    assert list(equality.x) == [0, 100] and list(equality.y) == [0, 100]
    # Lorenz starts at the origin and ends at (100, 100).
    assert lorenz.x[0] == 0 and lorenz.y[0] == 0
    assert lorenz.x[-1] == 100 and round(lorenz.y[-1]) == 100
    # Perfect equality → curve sits on the diagonal → Gini ~0 in the title.
    assert "Gini 0.00" in fig.layout.title.text


def test_recruiter_concentration_curve_concentrated():
    """A skewed distribution should report a high Gini and a top-10 share, and
    the curve should bow well below equality (cumulative ys < xs)."""
    rows = [{"institution": f"Small {i}", "job_count": 1} for i in range(20)]
    rows.append({"institution": "Dominant", "job_count": 200})
    fig = charts.recruiter_concentration_curve(rows)
    lorenz = fig.data[1]
    # Mid-distribution the small recruiters hold only a tiny share of postings.
    mid = len(lorenz.x) // 2
    assert lorenz.y[mid] < lorenz.x[mid]
    title = fig.layout.title.text
    assert "Gini" in title and "top 10" in title


def test_recruiter_concentration_curve_empty():
    fig = charts.recruiter_concentration_curve([])
    assert len(fig.data) == 0
    assert any("data" in (a.text or "").lower() for a in fig.layout.annotations)


def test_transparency_breakdown_two_panels_baseline_and_intl_colour():
    """salary_transparency_breakdown draws one bar panel per dimension, a dashed
    baseline on each, and flags International in the negative colour."""
    rows = [
        {"grp": "computer-sciences", "dim": "discipline", "n": 40, "undisclosed": 4, "undisclosed_pct": 10.0},
        {"grp": "law", "dim": "discipline", "n": 22, "undisclosed": 11, "undisclosed_pct": 50.0},
        {"grp": "England", "dim": "region", "n": 120, "undisclosed": 18, "undisclosed_pct": 15.0},
        {"grp": "International", "dim": "region", "n": 30, "undisclosed": 30, "undisclosed_pct": 100.0},
    ]
    fig = charts.salary_transparency_breakdown(rows)
    bars = [t for t in fig.data if t.type == "bar"]
    assert len(bars) == 2, "one horizontal-bar panel for disciplines, one for regions"
    # Two dashed baseline reference lines, one per panel.
    assert len(fig.layout.shapes) == 2
    # The discipline panel should humanise slugs to display labels.
    disc_labels = list(bars[0].y)
    assert "Law" in disc_labels
    assert "law" not in disc_labels
    # International is highlighted in the negative colour; England is not.
    region_panel = bars[1]
    by_region = dict(zip(region_panel.y, region_panel.marker.color))
    assert by_region["International"] == charts._NEG
    assert by_region["England"] == charts._ACCENT


def test_transparency_breakdown_drops_thin_groups():
    """Groups below the min-N threshold are dropped before plotting."""
    rows = [
        {"grp": "England", "dim": "region", "n": 120, "undisclosed": 18, "undisclosed_pct": 15.0},
        {"grp": "Northern Ireland", "dim": "region", "n": 3, "undisclosed": 0, "undisclosed_pct": 0.0},
    ]
    fig = charts.salary_transparency_breakdown(rows)
    bars = [t for t in fig.data if t.type == "bar"]
    region_bar = next(b for b in bars if "England" in list(b.y))
    assert "Northern Ireland" not in list(region_bar.y), "thin group should be filtered out"


def test_transparency_breakdown_empty():
    fig = charts.salary_transparency_breakdown([])
    assert len(fig.data) == 0


def test_intl_vs_uk_profile_grouped_shares():
    """Two coloured series (International vs UK), one grouped bar per share
    metric, all on a 0-100% scale — and never a median-£ value.
    """
    rows = [
        {"side": "International", "total": 11, "pct_permanent": 81.8,
         "pct_fixed_term": 18.2, "pct_full_time": 90.9, "pct_part_time": 9.1,
         "pct_salary_disclosed": 0.0},
        {"side": "UK", "total": 95, "pct_permanent": 57.9,
         "pct_fixed_term": 42.1, "pct_full_time": 83.2, "pct_part_time": 13.7,
         "pct_salary_disclosed": 93.7},
    ]
    fig = charts.intl_vs_uk_profile_bars(rows)
    assert fig.layout.barmode == "group"
    assert len(fig.data) == 2, "one bar series per side"
    sides = {t.name.split(" (")[0] for t in fig.data}
    assert sides == {"UK", "International"}
    # Every plotted value is a share in [0, 100] — no raw £ figures leak in.
    for trace in fig.data:
        assert trace.orientation == "h"
        assert all(0 <= x <= 100 for x in trace.x), trace.x
    # The salary-disclosure gap must be represented (International 0% vs UK ~94%).
    by_side = {t.name.split(" (")[0]: t for t in fig.data}
    disclosure_label = "Salary disclosed"
    intl_x = dict(zip(by_side["International"].y, by_side["International"].x))
    uk_x = dict(zip(by_side["UK"].y, by_side["UK"].x))
    assert intl_x[disclosure_label] == 0.0
    assert uk_x[disclosure_label] > 90


def test_intl_vs_uk_profile_needs_both_sides():
    """Placeholder when one side is missing — can't compare a single side."""
    fig = charts.intl_vs_uk_profile_bars(
        [{"side": "UK", "total": 95, "pct_permanent": 57.9, "pct_fixed_term": 42.1,
          "pct_full_time": 83.2, "pct_part_time": 13.7, "pct_salary_disclosed": 93.7}]
    )
    assert len(fig.data) == 0


def test_intl_vs_uk_profile_placeholder_when_empty():
    fig = charts.intl_vs_uk_profile_bars([])
    assert len(fig.data) == 0


def test_casualisation_bar_diverges_around_baseline():
    """Bars are anchored at the sample-weighted market baseline; disciplines above
    the baseline colour _NEG (more casualised), below colour _POS, and bars are
    ordered ascending by fixed-term %.
    """
    rows = [
        {"category": "computer-sciences", "n": 100, "fixed_term_pct": 30.0},
        {"category": "health-and-medical", "n": 100, "fixed_term_pct": 70.0},
    ]
    fig = charts.casualisation_by_discipline_bar(rows)
    bar = fig.data[0]
    assert bar.type == "bar"
    assert bar.orientation == "h"
    # Equal n → baseline is the simple mean of the two shares.
    assert bar.base == 50.0
    # Sorted ascending by fixed-term %: lower share first.
    assert list(bar.y) == ["Computer Sciences", "Health & Medical"]
    # Deltas are measured from the baseline.
    assert list(bar.x) == [-20.0, 20.0]
    # Below-baseline → _POS (green), above-baseline → _NEG (red).
    assert list(bar.marker.color) == [charts._POS, charts._NEG]
    # Baseline drawn as a reference line.
    assert any(s.line.dash == "dash" for s in fig.layout.shapes)


def test_casualisation_bar_placeholder_when_empty():
    fig = charts.casualisation_by_discipline_bar([])
    assert len(fig.data) == 0
    assert any("data" in (a.text or "").lower() for a in fig.layout.annotations)


def test_application_window_by_discipline_bar_renders_dots_and_reference():
    """Median dot per discipline, an IQR whisker per discipline, and a single
    market-median reference line."""
    rows = [
        {"category": "computer-sciences", "median_days": 21.0, "p25": 14.0,
         "p75": 30.0, "n": 25, "market_median": 19.0},
        {"category": "law", "median_days": 14.0, "p25": 10.0,
         "p75": 20.0, "n": 12, "market_median": 19.0},
    ]
    fig = charts.application_window_by_discipline_bar(rows)
    # One whisker line per discipline + one marker trace for the median dots.
    marker_traces = [t for t in fig.data if getattr(t.marker, "size", None)]
    assert len(marker_traces) == 1
    dots = marker_traces[0]
    assert dots.mode == "markers"
    assert len(dots.x) == 2, "one median dot per discipline"
    line_traces = [t for t in fig.data if t.mode == "lines"]
    assert len(line_traces) == 2, "one IQR whisker per discipline"
    # Reference line at the market median.
    vlines = [s for s in fig.layout.shapes if s.line.dash == "dash"]
    assert vlines and vlines[0].x0 == 19.0


def test_application_window_by_discipline_bar_placeholder_when_empty():
    fig = charts.application_window_by_discipline_bar([])
    assert len(fig.data) == 0
    assert any("posting" in (a.text or "").lower() or "data" in (a.text or "").lower()
               for a in fig.layout.annotations)


def test_precarity_matrix_heatmap_annotates_and_outlines():
    """The matrix renders a heatmap with one annotation per cell (count + %)
    and outlines the fixed-term + part-time doubly-precarious cell."""
    rows = [
        {"contract_type": "permanent",  "hours": "full-time", "job_count": 57},
        {"contract_type": "permanent",  "hours": "part-time", "job_count": 5},
        {"contract_type": "permanent",  "hours": "flexible",  "job_count": 2},
        {"contract_type": "fixed-term", "hours": "full-time", "job_count": 32},
        {"contract_type": "fixed-term", "hours": "part-time", "job_count": 9},
        {"contract_type": "fixed-term", "hours": "flexible",  "job_count": 1},
    ]
    fig = charts.precarity_matrix_heatmap(rows)
    assert fig.data[0].type == "heatmap"
    # 2 contract types x 3 hours = 6 cells, one annotation each (title is layout
    # text, not a layout.annotation), so exactly 6 cell annotations.
    assert len(fig.layout.annotations) == 6
    # n=106 should appear in the title subtitle.
    assert "106" in fig.layout.title.text
    # One rectangle shape outlines the doubly-precarious cell.
    rects = [s for s in fig.layout.shapes if s.type == "rect"]
    assert len(rects) == 1


def test_precarity_matrix_heatmap_placeholder_when_empty():
    fig = charts.precarity_matrix_heatmap([])
    assert len(fig.data) == 0
    assert any("contract" in (a.text or "").lower() for a in fig.layout.annotations)


# Add to tests/test_charts.py

def test_deadline_pressure_orders_buckets_and_colours_by_urgency():
    """Bands must render in fixed urgency order (0-3 first) on a red->green ramp,
    regardless of the order the query returns them in."""
    rows = [
        {"bucket": "30+", "job_count": 3},
        {"bucket": "0-3", "job_count": 14},
        {"bucket": "8-14", "job_count": 13},
        {"bucket": "4-7", "job_count": 8},
        {"bucket": "15-30", "job_count": 2},
    ]
    fig = charts.deadline_pressure_bar(rows)
    bar = fig.data[0]
    assert bar.type == "bar"
    assert list(bar.x) == ["0-3 days", "4-7 days", "8-14 days", "15-30 days", "30+ days"]
    assert list(bar.y) == [14, 8, 13, 2, 3]
    # Most-urgent band is red (_NEG); least-urgent is green (_POS).
    assert bar.marker.color[0] == charts._NEG
    assert bar.marker.color[-1] == charts._POS


def test_deadline_pressure_placeholder_when_empty():
    assert len(charts.deadline_pressure_bar([]).data) == 0
    # All-zero bands (open-jobs table empty) also fall back to the placeholder.
    zero_rows = [{"bucket": b, "job_count": 0}
                 for b in ["0-3", "4-7", "8-14", "15-30", "30+"]]
    assert len(charts.deadline_pressure_bar(zero_rows).data) == 0
