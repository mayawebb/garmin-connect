from datetime import datetime, timedelta

from garmin_dashboard.analytics import (
    average_weekly_running_distance,
    estimate_lactate_threshold,
    format_duration_seconds,
    format_pace_min_km,
    median_running_pace,
    predicted_5k_trend,
    weekly_running_distance_calendar,
    weekly_running_distance,
)
from garmin_dashboard.activity_streams import ActivityStreamPoint
from garmin_dashboard.models import Activity


def test_weekly_running_distance_aggregates_only_running_records():
    activities = [
        Activity("r1", datetime(2026, 11, 9), "running", distance_m=5000),
        Activity("r2", datetime(2026, 11, 11), "treadmill_running", distance_m=3000),
        Activity("y1", datetime(2026, 11, 10), "yoga", duration_s=3600),
    ]
    rows = weekly_running_distance(activities)
    assert rows == [{"week_start": datetime(2026, 11, 9).date(), "distance_km": 5.0, "run_count": 1}]


def test_predicted_5k_trend_uses_recorded_run_efforts_and_excludes_treadmill():
    activities = [
        Activity("road", datetime(2026, 11, 9), "running", distance_m=5000, duration_s=1500),
        Activity("treadmill", datetime(2026, 11, 10), "treadmill_running", distance_m=5000, duration_s=1200),
        Activity("walk", datetime(2026, 11, 11), "walking", distance_m=5000, duration_s=1800),
    ]
    rows = predicted_5k_trend(activities)
    assert len(rows) == 1
    assert rows[0]["activity_id"] == "road"
    assert rows[0]["predicted_5k_seconds"] == 1500


def test_running_summary_uses_median_pace_and_calendar_week_average():
    activities = [
        Activity("r1", datetime(2026, 11, 2), "running", distance_m=5000, duration_s=1800),
        Activity("r2", datetime(2026, 11, 4), "running", distance_m=10000, duration_s=3000),
        Activity("r3", datetime(2026, 11, 9), "running", distance_m=5000, duration_s=1200),
        Activity("treadmill", datetime(2026, 11, 10), "treadmill_running", distance_m=3000, duration_s=900),
    ]
    assert median_running_pace(activities) == 5.0
    assert average_weekly_running_distance(activities) == 10.0


def test_calendar_week_distance_shows_weeks_without_runs_as_zero():
    activities = [
        Activity("r1", datetime(2026, 11, 2), "running", distance_m=5000),
        Activity("y1", datetime(2026, 11, 9), "yoga", duration_s=3600),
        Activity("r2", datetime(2026, 11, 16), "running", distance_m=3000),
    ]

    assert weekly_running_distance_calendar(activities) == [
        {"week_start": datetime(2026, 11, 2).date(), "distance_km": 5.0, "run_count": 1},
        {"week_start": datetime(2026, 11, 9).date(), "distance_km": 0.0, "run_count": 0},
        {"week_start": datetime(2026, 11, 16).date(), "distance_km": 3.0, "run_count": 1},
    ]
    assert average_weekly_running_distance(activities) == 8 / 3


def test_pace_formatter_converts_decimal_minutes_to_clock_time():
    assert format_pace_min_km(6.63) == "6:38 /km"
    assert format_pace_min_km(6.999) == "7:00 /km"
    assert format_pace_min_km(None) == "Unavailable"
    assert format_pace_min_km(float("nan")) == "Unavailable"


def test_duration_formatter_uses_minutes_and_hours_without_decimal_units():
    assert format_duration_seconds(1594) == "26:34"
    assert format_duration_seconds(3662) == "1:01:02"
    assert format_duration_seconds(float("nan")) == "Unavailable"


def test_lactate_threshold_requires_a_confirmed_30_minute_test_with_sensor_coverage():
    start = datetime(2026, 11, 12, 7)
    points = [
        ActivityStreamPoint(start + timedelta(seconds=second), 160, second * 3, 3.0, 85, 10.0)
        for second in range(0, 1801, 60)
    ]
    estimate = estimate_lactate_threshold(1800, points, confirmed_threshold_test=True)
    assert estimate is not None
    assert estimate.heart_rate_bpm == 160
    assert round(estimate.pace_min_km, 2) == 5.56
    assert estimate.method == "30-minute field test; final 20-minute average"


def test_lactate_threshold_refuses_short_or_unconfirmed_efforts():
    start = datetime(2026, 11, 12, 7)
    points = [
        ActivityStreamPoint(start + timedelta(seconds=second), 160, second, 3.0, 80, 8.0)
        for second in range(0, 1801, 60)
    ]
    assert estimate_lactate_threshold(1800, points, confirmed_threshold_test=False) is None
    assert estimate_lactate_threshold(1200, points, confirmed_threshold_test=True) is None
