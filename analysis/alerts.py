"""Check analysis results against configured thresholds and emit alerts."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from config import ALERT_THRESHOLDS, CATEGORY_LABELS
from analysis.institutions import spike_candidates
from analysis.trends import category_growth_wow


def _friendly_cats(category_list: str) -> str:
    """Convert 'academic-or-research,further-education' to readable labels."""
    return ", ".join(
        CATEGORY_LABELS.get(s.strip(), s.strip())
        for s in category_list.split(",")
        if s.strip()
    )


Severity = Literal["info", "warning", "critical"]


@dataclass
class Alert:
    type: str
    severity: Severity
    message: str
    data: dict = field(default_factory=dict)
    raised_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def as_dict(self) -> dict:
        return {
            "type":      self.type,
            "severity":  self.severity,
            "message":   self.message,
            "data":      self.data,
            "raised_at": self.raised_at,
        }


def check_institution_spikes(days: int = 7) -> list[Alert]:
    """Alert when a single institution posts heavily in a rolling window."""
    threshold = ALERT_THRESHOLDS["institution_weekly_jobs"]
    candidates = spike_candidates(days=days, threshold=threshold)
    alerts = []
    for row in candidates:
        severity: Severity = "critical" if row["job_count"] >= threshold * 2 else "warning"
        cat_word = "category" if row["categories"] == 1 else "categories"
        alerts.append(
            Alert(
                type="institution_spike",
                severity=severity,
                message=(
                    f"{row['institution']} posted {row['job_count']} jobs "
                    f"in the last {days} days "
                    f"({row['categories']} {cat_word}: "
                    f"{_friendly_cats(row['category_list'])})"
                ),
                data=dict(row),
            )
        )
    return alerts


def check_category_growth() -> list[Alert]:
    """Alert when a category grows or shrinks significantly week-on-week."""
    threshold = ALERT_THRESHOLDS["category_growth_pct"]
    growth = category_growth_wow()
    alerts = []
    for row in growth:
        pct = row["change_pct"]
        if pct is None:
            continue
        label = CATEGORY_LABELS.get(row["category"], row["category"])
        if abs(pct) >= threshold:
            direction = "up" if pct > 0 else "down"
            severity: Severity = "warning" if abs(pct) >= threshold * 2 else "info"
            alerts.append(
                Alert(
                    type="category_growth",
                    severity=severity,
                    message=(
                        f"{label} is {direction} {abs(pct):.1f}% week-on-week "
                        f"({row['last_week']} → {row['this_week']} jobs)"
                    ),
                    data=dict(row),
                )
            )
    return alerts


def check_all() -> list[Alert]:
    """Run all checks and return a combined, severity-sorted alert list."""
    alerts: list[Alert] = []
    alerts.extend(check_institution_spikes())
    alerts.extend(check_category_growth())

    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(alerts, key=lambda a: order[a.severity])


def print_alerts(alerts: list[Alert]) -> None:
    if not alerts:
        print("No alerts.")
        return
    markers = {"critical": "[!!]", "warning": "[! ]", "info": "[ i]"}
    for a in alerts:
        marker = markers.get(a.severity, "[  ]")
        print(f"  {marker} [{a.severity.upper()}] {a.message}")
