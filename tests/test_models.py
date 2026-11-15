from datetime import datetime, timezone

import pytest

from garmin_dashboard.models import Activity


def test_activity_accepts_optional_metrics_and_retains_source_fields():
    activity = Activity(
        activity_id="sample-1",
        started_at=datetime(2026, 3, 1, 7, 30, tzinfo=timezone.utc),
        activity_type="running",
        distance_m=5000,
        duration_s=1500,
        elevation_gain_m=None,
        average_heart_rate_bpm=None,
        source_fields={"source": "synthetic"},
    )

    assert activity.distance_km == 5
    assert activity.elevation_gain_m is None
    assert activity.average_heart_rate_bpm is None
    assert activity.source_fields["source"] == "synthetic"


@pytest.mark.parametrize(
    "overrides",
    [
        {"activity_id": ""},
        {"distance_m": -1},
        {"duration_s": -1},
        {"average_heart_rate_bpm": 0},
    ],
)
def test_activity_rejects_invalid_values(overrides):
    values = {
        "activity_id": "sample-1",
        "started_at": datetime(2026, 3, 1, tzinfo=timezone.utc),
        "activity_type": "running",
        "distance_m": 5000,
        "duration_s": 1500,
    }
    values.update(overrides)

    with pytest.raises(ValueError):
        Activity(**values)
