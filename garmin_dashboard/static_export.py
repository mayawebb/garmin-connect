"""Privacy-limited, browser-importable export for the static Pages dashboard."""

from datetime import date, datetime
from typing import Any

from .models import Activity


def build_static_export(activities: list[Activity], health_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return only curated fields; omit Garmin IDs, raw fields, and treadmill runs."""
    activity_rows = []
    for activity in activities:
        if "treadmill" in activity.activity_type.casefold():
            continue
        activity_rows.append({
            "date": activity.started_at.isoformat(),
            "type": activity.activity_type,
            "distance_km": activity.distance_km,
            "duration_s": activity.duration_s,
            "elevation_m": activity.elevation_gain_m,
            "average_hr_bpm": activity.average_heart_rate_bpm,
        })

    curated_health = []
    for row in health_rows:
        day = row.get("Date")
        if isinstance(day, (datetime, date)):
            day = day.isoformat()
        value = row.get("Value")
        curated_health.append({
            "date": str(day)[:10] if day is not None else None,
            "metric": row.get("Metric"),
            "value": float(value) if value is not None else None,
            "unit": row.get("Unit"),
        })

    return {"schema_version": 1, "activities": activity_rows, "health": curated_health}
