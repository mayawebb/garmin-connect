"""Null-aware activity and running calculations."""

from dataclasses import dataclass
from datetime import timedelta
from statistics import fmean, median

from .activity_streams import ActivityStreamPoint
from .models import Activity


def pace_minutes_per_km(distance_km: float | None, duration_seconds: float | None) -> float | None:
    """Return elapsed pace in min/km, or None when inputs cannot produce it."""
    if distance_km is None or duration_seconds is None or distance_km <= 0 or duration_seconds <= 0:
        return None
    return duration_seconds / 60 / distance_km


def is_running_type(activity_type: str) -> bool:
    """Return whether a type is an outdoor/road running activity."""
    normalized = activity_type.lower()
    return "run" in normalized and "treadmill" not in normalized


def weekly_running_distance(activities: list[Activity]) -> list[dict]:
    """Return weekly distance and activity count for recorded running activities."""
    weeks: dict = {}
    for activity in activities:
        if not is_running_type(activity.activity_type):
            continue
        week_start = activity.started_at.date() - timedelta(days=activity.started_at.weekday())
        row = weeks.setdefault(week_start, {"week_start": week_start, "distance_km": None, "run_count": 0})
        row["run_count"] += 1
        if activity.distance_km is not None:
            row["distance_km"] = (row["distance_km"] or 0.0) + activity.distance_km
    return [weeks[week] for week in sorted(weeks)]


def median_running_pace(activities: list[Activity]) -> float | None:
    """Return the median recorded outdoor-run pace in minutes per kilometer."""
    paces = [
        pace for activity in activities
        if is_running_type(activity.activity_type)
        for pace in [pace_minutes_per_km(activity.distance_km, activity.duration_s)]
        if pace is not None
    ]
    return median(paces) if paces else None


def average_weekly_running_distance(activities: list[Activity]) -> float | None:
    """Average known distances over weeks containing outdoor runs with distance."""
    weekly = weekly_running_distance(activities)
    observed_weeks = [row["distance_km"] for row in weekly if row["distance_km"] is not None]
    return fmean(observed_weeks) if observed_weeks else None


def predicted_5k_trend(activities: list[Activity]) -> list[dict]:
    """Estimate 5K-equivalent times from road runs of at least 2 km.

    This uses the Riegel distance-duration relation for each activity, so it is
    a rough performance indicator rather than a guaranteed race result.
    """
    rows = []
    for activity in activities:
        distance_km = activity.distance_km
        duration = activity.duration_s
        if not is_running_type(activity.activity_type):
            continue
        if distance_km is None or duration is None or distance_km < 2 or duration <= 0:
            continue
        estimate = duration * (5 / distance_km) ** 1.06
        rows.append({
            "activity_id": activity.activity_id,
            "date": activity.started_at,
            "source_distance_km": distance_km,
            "predicted_5k_seconds": estimate,
        })
    return sorted(rows, key=lambda row: row["date"])


@dataclass(frozen=True)
class LactateThresholdEstimate:
    pace_min_km: float
    heart_rate_bpm: float
    method: str = "30-minute field test; final 20-minute average"


def estimate_lactate_threshold(
    duration_s: float,
    points: list[ActivityStreamPoint],
    *,
    confirmed_threshold_test: bool,
) -> LactateThresholdEstimate | None:
    """Estimate field-test pace/HR; requires user confirmation and 20 minutes of samples."""
    if not confirmed_threshold_test or duration_s < 1800:
        return None
    timestamps = [point.timestamp for point in points if point.timestamp is not None]
    if not timestamps:
        return None
    start = min(timestamps)
    segment = [
        point for point in points
        if point.timestamp is not None
        and (point.timestamp - start).total_seconds() >= duration_s - 1200
        and (point.timestamp - start).total_seconds() <= duration_s
        and point.heart_rate_bpm is not None
        and point.speed_mps is not None
        and point.speed_mps > 0
    ]
    if len(segment) < 20:
        return None
    covered_s = (max(p.timestamp for p in segment) - min(p.timestamp for p in segment)).total_seconds()
    if covered_s < 19 * 60:
        return None
    mean_speed = sum(point.speed_mps for point in segment) / len(segment)
    if mean_speed <= 0:
        return None
    mean_hr = sum(point.heart_rate_bpm for point in segment) / len(segment)
    return LactateThresholdEstimate(1000 / mean_speed / 60, mean_hr)
