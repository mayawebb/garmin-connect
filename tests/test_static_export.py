from datetime import date, datetime, timezone

from garmin_dashboard.models import Activity
from garmin_dashboard.static_export import build_static_export


def test_static_export_keeps_curated_metrics_and_drops_identifiers_and_treadmill():
    activities = [
        Activity(
            activity_id="secret-garmin-id",
            started_at=datetime(2026, 11, 10, 7, tzinfo=timezone.utc),
            activity_type="running",
            distance_m=5000,
            duration_s=1800,
            elevation_gain_m=20,
            average_heart_rate_bpm=150,
            source_fields={"userProfilePK": 123, "raw": "private"},
        ),
        Activity(
            activity_id="treadmill-id",
            started_at=datetime(2026, 11, 11, 7, tzinfo=timezone.utc),
            activity_type="treadmill_running",
            distance_m=4000,
            duration_s=1500,
        ),
    ]
    data = build_static_export(activities, [{"Date": date(2026, 11, 10), "Metric": "Sleep score", "Value": 80, "Unit": "score"}])

    assert data["schema_version"] == 1
    assert len(data["activities"]) == 1
    assert data["activities"][0] == {
        "date": "2026-11-10T07:00:00+00:00",
        "type": "running",
        "distance_km": 5.0,
        "duration_s": 1800,
        "elevation_m": 20,
        "average_hr_bpm": 150,
    }
    assert data["health"][0]["date"] == "2026-11-10"
    serialized = str(data)
    assert "secret-garmin-id" not in serialized
    assert "userProfilePK" not in serialized


def test_static_export_preserves_missing_values_as_null():
    activity = Activity(
        activity_id="a1",
        started_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
        activity_type="cycling",
        duration_s=600,
    )
    data = build_static_export([activity], [])
    assert data["activities"][0]["distance_km"] is None
    assert data["activities"][0]["average_hr_bpm"] is None
