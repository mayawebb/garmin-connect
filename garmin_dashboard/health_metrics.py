"""Curated health series from documented, present Garmin fields."""

from .models import Activity
from .analytics import is_running_type
from .wellness import WellnessMetricPoint


SERIES = {
    "Steps": ("daily_summaries.movement.steps.value", 1.0, "steps"),
    "Resting heart rate": ("daily_summaries.heartRate.restingValue", 1.0, "bpm"),
    "Daily minimum heart rate": ("daily_summaries.heartRate.minValue", 1.0, "bpm"),
    "Daily maximum heart rate": ("daily_summaries.heartRate.maxValue", 1.0, "bpm"),
    "Body Battery": ("daily_summaries.bodyBattery.latestValue", 1.0, "score"),
    "Body Battery charged": ("daily_summaries.bodyBattery.chargedValue", 1.0, "score"),
    "Average stress": ("daily_summaries.stress.avgLevel", 1.0, "level"),
    "Average respiration": ("daily_summaries.respiration.avgValue", 1.0, "breaths/min"),
    "Sleep score": ("sleep_summaries.sleepScores.overall.value", 1.0, "score"),
    "Sleep duration": ("sleep_summaries.sleepTimeSeconds", 1 / 3600, "hours"),
    "Deep sleep": ("sleep_summaries.deepSleepSeconds", 1 / 3600, "hours"),
    "REM sleep": ("sleep_summaries.remSleepSeconds", 1 / 3600, "hours"),
    "Average heart rate during sleep": ("sleep_summaries.avgHeartRate", 1.0, "bpm"),
    "Nightly HRV": ("hrv_summaries.lastNightAvg", 1.0, "ms"),
    "Weekly HRV average": ("hrv_summaries.weeklyAvg", 1.0, "ms"),
}


def health_trend_rows(points: list[WellnessMetricPoint], activities: list[Activity]) -> list[dict]:
    rows = []
    metric_labels = {source_name: (label, factor, unit) for label, (source_name, factor, unit) in SERIES.items()}
    for point in points:
        if point.metric in metric_labels:
            label, factor, unit = metric_labels[point.metric]
            rows.append({"Date": point.day, "Metric": label, "Value": point.value * factor, "Unit": unit})
    for activity in activities:
        if is_running_type(activity.activity_type) and activity.average_heart_rate_bpm is not None:
            rows.append({
                "Date": activity.started_at,
                "Metric": "Average heart rate on runs",
                "Value": float(activity.average_heart_rate_bpm),
                "Unit": "bpm",
            })
    return rows
