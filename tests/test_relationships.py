from datetime import date, datetime

from garmin_dashboard.models import Activity
from garmin_dashboard.wellness import WellnessMetricPoint
from garmin_dashboard.relationships import match_wellness_to_activities


def test_matches_previous_day_recovery_to_activity_and_omits_missing_metrics():
    activity = Activity(
        "run-1", datetime(2026, 3, 2, 7), "running", distance_m=5000,
        duration_s=1500, average_heart_rate_bpm=145,
    )
    points = [
        WellnessMetricPoint(date(2026, 3, 1), "hrv.avg", 58),
        WellnessMetricPoint(date(2026, 3, 1), "sleep.duration", 7.5),
    ]

    rows = match_wellness_to_activities([activity], points)

    pace_rows = [row for row in rows if row["Activity metric"] == "Pace (min/km)"]
    assert pace_rows == [
        {"Date": date(2026, 3, 2), "Activity": "run-1", "Type": "running",
         "Wellness metric": "hrv.avg", "Wellness value": 58.0,
         "Activity metric": "Pace (min/km)", "Activity value": 5.0},
        {"Date": date(2026, 3, 2), "Activity": "run-1", "Type": "running",
         "Wellness metric": "sleep.duration", "Wellness value": 7.5,
         "Activity metric": "Pace (min/km)", "Activity value": 5.0},
    ]


def test_does_not_create_relationship_for_wellness_on_unmatched_date():
    activity = Activity("run-1", datetime(2026, 3, 2, 7), "running")
    points = [WellnessMetricPoint(date(2026, 3, 2), "restingHeartRate", 52)]
    assert match_wellness_to_activities([activity], points) == []
