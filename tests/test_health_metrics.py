from datetime import date, datetime

from garmin_dashboard.health_metrics import health_trend_rows, sleep_run_association
from garmin_dashboard.models import Activity
from garmin_dashboard.wellness import WellnessMetricPoint


def test_health_trends_include_curated_wellness_and_run_heart_rate_only_when_present():
    activities = [
        Activity("r1", datetime(2026, 1, 2), "running", average_heart_rate_bpm=144),
        Activity("tr1", datetime(2026, 1, 2), "treadmill_running", average_heart_rate_bpm=155),
        Activity("r2", datetime(2026, 1, 3), "cycling", average_heart_rate_bpm=120),
    ]
    points = [
        WellnessMetricPoint(date(2026, 1, 1), "sleep_summaries.sleepScores.overall.value", 82),
        WellnessMetricPoint(date(2026, 1, 1), "daily_summaries.movement.steps.value", 7000),
        WellnessMetricPoint(date(2026, 1, 2), "daily_summaries.heartRate.restingValue", 55),
    ]
    rows = health_trend_rows(points, activities)
    assert {row["Metric"] for row in rows} == {"Sleep score", "Steps", "Resting heart rate", "Average heart rate on runs"}
    assert {row["Value"] for row in rows} == {82.0, 7000.0, 55.0, 144.0}
    assert all(row["Metric"] != "Average heart rate on runs" or row["Date"].date() == date(2026, 1, 2) for row in rows)


def test_sleep_run_association_uses_same_day_outdoor_runs_and_reports_groups():
    activities = [
        Activity("low", datetime(2026, 1, 1), "running", distance_m=5000, duration_s=1800, average_heart_rate_bpm=160),
        Activity("high", datetime(2026, 1, 2), "running", distance_m=5000, duration_s=1800, average_heart_rate_bpm=158),
        Activity("treadmill", datetime(2026, 1, 2), "treadmill_running", distance_m=5000, duration_s=1600, average_heart_rate_bpm=170),
    ]
    points = [
        WellnessMetricPoint(date(2026, 1, 1), "sleep_summaries.sleepScores.overall.value", 60),
        WellnessMetricPoint(date(2026, 1, 2), "sleep_summaries.sleepScores.overall.value", 90),
    ]

    result = sleep_run_association(activities, points)

    assert result["matched_run_count"] == 2
    assert result["sleep_score_median"] == 75
    assert result["groups"]["At or below median"]["run_count"] == 1
    assert result["groups"]["Above median"]["median_heart_rate_bpm"] == 158
