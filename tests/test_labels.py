"""Tests for the single-source slug->label resolver (config.discipline_label) and
its re-exports in the dashboard layer."""

import pytest

from config import discipline_label, CATEGORY_LABELS


def test_known_disciplines_verbatim():
    # A known slug returns its CATEGORY_LABELS display name unchanged.
    slug, label = next(iter(CATEGORY_LABELS.items()))
    assert discipline_label(slug) == label
    assert discipline_label("computer-sciences") == "Computer Sciences"


@pytest.mark.parametrize("slug, expected", [
    ("academic-or-research", "Academic or Research"),
    ("professional-or-managerial", "Professional or Managerial"),
    ("further-education", "Further Education"),
    ("craft-or-manual", "Craft or Manual"),
    ("technical", "Technical"),
])
def test_legacy_slugs_humanised(slug, expected):
    assert discipline_label(slug) == expected


@pytest.mark.parametrize("slug, expected", [
    ("uk-wide", "UK Wide"),
    ("it-services", "IT Services"),
    ("eu-funded", "EU Funded"),
])
def test_acronyms_uppercased(slug, expected):
    assert discipline_label(slug) == expected


def test_unknown_slug_prettified_not_dumped():
    assert discipline_label("some-new-thing") == "Some New Thing"
    # never returns raw kebab-case for a multi-word slug
    assert "-" not in discipline_label("a-b-c")


def test_dashboard_reexports_share_the_resolver():
    from dashboard.charts import category_label, _label
    assert category_label is discipline_label
    assert _label("academic-or-research") == "Academic or Research"
    assert _label("__other__") == "Other disciplines"


def test_alerts_layer_has_no_dashboard_import():
    # Layering guard: the analysis/alerts module must resolve labels via config,
    # never by importing the dashboard package.
    import analysis.alerts as alerts
    src = alerts.__file__
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "import dashboard" not in text
    assert "from dashboard" not in text
