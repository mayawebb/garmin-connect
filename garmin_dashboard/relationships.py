"""Exploratory wellness-to-next-day activity comparisons."""

from datetime import timedelta

from .models import Activity
from .wellness import WellnessMetricPoint


def match_wellness_to_activities(
    activities: list[Activity],
    wellness_points: list[WellnessMetricPoint],
    *,
    prior_days: int = 1,
) -> list[dict]:
    """Pair a wellness day with activity metrics on a later day (default: next day).

    This is a descriptive comparison, not a causal training or recovery score.
    Missing activity measurements are omitted rather than imputed.
    """
    if prior_days < 0:
        raise ValueError("prior_days must be non-negative")
    points_by_day: dict = {}
    for point in wellness_points:
        points_by_day.setdefault(point.day, []).append(point)

    rows = []
    for activity in activities:
        activity_day = activity.started_at.date()
        wellness_day = activity_day - timedelta(days=prior_days)
        for point in points_by_day.get(wellness_day, []):
            values = []
            if activity.distance_km is not None:
                values.append(("Distance (km)", activity.distance_km))
            if activity.duration_s is not None:
                values.append(("Duration (min)", activity.duration_s / 60))
            if activity.elevation_gain_m is not None:
                values.append(("Elevation gain (m)", activity.elevation_gain_m))
            if activity.average_heart_rate_bpm is not None:
                values.append(("Avg heart rate (bpm)", activity.average_heart_rate_bpm))
            if "run" in activity.activity_type.lower() and activity.distance_km and activity.duration_s is not None:
                values.append(("Pace (min/km)", activity.duration_s / 60 / activity.distance_km))
            for activity_metric, activity_value in values:
                rows.append({
                    "Date": activity_day,
                    "Activity": activity.activity_id,
                    "Type": activity.activity_type,
                    "Wellness metric": point.metric,
                    "Wellness value": point.value,
                    "Activity metric": activity_metric,
                    "Activity value": float(activity_value),
                })
    return rows
