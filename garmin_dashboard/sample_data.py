"""Synthetic multi-sport activities for trying the UI without credentials."""

from datetime import datetime, timedelta, timezone

from .models import Activity


def sample_activities() -> list[Activity]:
    rows = [
        ("s01", 5.1, 31.2, 28, 146), ("s02", 7.0, 41.8, 42, 151),
        ("s03", 12.0, 73.0, 65, 154), ("s04", 5.4, 32.0, 30, 145),
        ("s05", 8.2, 48.0, 50, 149), ("s06", 14.0, 84.5, 80, 156),
        ("s07", 5.0, 29.8, 22, 143), ("s08", 7.5, 44.0, None, 150),
        ("s09", 16.0, 96.0, 92, 157), ("s10", 5.8, 34.5, 31, None),
        ("s11", 9.0, 52.8, 47, 151), ("s12", 18.0, 109.0, 110, 159),
        ("s13", 6.0, 35.0, 26, 145), ("s14", 8.5, 49.5, 54, 150),
        ("s15", 20.0, 122.0, 135, 160), ("s16", 5.2, 30.0, 20, None),
    ]
    now = datetime.now(timezone.utc)
    activities = []
    for index, (activity_id, km, minutes, elevation, heart_rate) in enumerate(rows):
        days_ago = 42 - index * 2 - (index // 3)
        activities.append(Activity(
            activity_id=activity_id,
            started_at=(now - timedelta(days=days_ago)).replace(hour=6, minute=30, second=0, microsecond=0),
            activity_type="running",
            distance_m=km * 1000,
            duration_s=minutes * 60,
            elevation_gain_m=elevation,
            average_heart_rate_bpm=heart_rate,
            source_fields={"source": "synthetic"},
        ))
    activities.extend([
        Activity(
            activity_id="cycle-01",
            started_at=(now - timedelta(days=3)).replace(hour=7, minute=0, second=0, microsecond=0),
            activity_type="cycling",
            distance_m=24000,
            duration_s=3600,
            elevation_gain_m=210,
            average_heart_rate_bpm=138,
            source_fields={"source": "synthetic"},
        ),
        Activity(
            activity_id="swim-01",
            started_at=(now - timedelta(days=9)).replace(hour=18, minute=0, second=0, microsecond=0),
            activity_type="lap_swimming",
            distance_m=1500,
            duration_s=2700,
            source_fields={"source": "synthetic"},
        ),
        Activity(
            activity_id="strength-01",
            started_at=(now - timedelta(days=11)).replace(hour=17, minute=30, second=0, microsecond=0),
            activity_type="strength_training",
            duration_s=2400,
            average_heart_rate_bpm=112,
            source_fields={"source": "synthetic"},
        ),
    ])
    return activities
