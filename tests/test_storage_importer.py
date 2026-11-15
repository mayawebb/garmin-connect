from datetime import datetime, timezone

from garmin_dashboard.importer import sync_activities
from garmin_dashboard.models import Activity
from garmin_dashboard.storage import ActivityRepository


def test_repository_upserts_once_and_keeps_missing_metrics_null(tmp_path):
    repository = ActivityRepository(tmp_path / "activities.sqlite3")
    repository.initialize()
    activity = Activity(
        activity_id="42",
        started_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        activity_type="running",
        distance_m=5000,
        duration_s=1500,
        source_fields={"activityId": 42},
    )

    assert repository.upsert(activity) == "inserted"
    assert repository.upsert(activity) == "unchanged"
    saved = repository.list_activities()[0]
    assert saved.activity_id == "42"
    assert saved.average_heart_rate_bpm is None
    assert saved.source_fields == {"activityId": 42}


def test_sync_reports_imported_skipped_and_failed_records(tmp_path):
    class Client:
        def iter_activities(self, **_kwargs):
            return iter([
                {"activityId": 1, "startTimeLocal": "2026-03-01T07:00:00", "activityTypeDTO": {"typeKey": "running"}, "summaryDTO": {"distance": 5000, "duration": 1500}},
                {"activityId": 1, "startTimeLocal": "2026-03-01T07:00:00", "activityTypeDTO": {"typeKey": "running"}, "summaryDTO": {"distance": 5000, "duration": 1500}},
                {"activityId": 2, "activityTypeDTO": {"typeKey": "running"}},
            ])

    repository = ActivityRepository(tmp_path / "activities.sqlite3")
    repository.initialize()

    report = sync_activities(Client(), repository)

    assert report.imported == 1
    assert report.skipped == 1
    assert report.failed == 1
    assert report.errors[0].startswith("Record 3:")

    class EmptyClient:
        def iter_activities(self, **kwargs):
            assert kwargs["start_date"].isoformat() == "2026-02-28"
            return iter([])

    sync_activities(EmptyClient(), repository)


def test_activity_mapping_accepts_personal_api_activity_type_shape():
    from garmin_dashboard.importer import activity_from_api

    activity = activity_from_api({
        "activityId": 99,
        "startTimeLocal": "2026-08-17T06:30:00",
        "activityType": {"typeKey": "running", "typeId": 1, "parentTypeId": 1},
        "distance": 8000,
        "duration": 2400,
        "averageHR": 150,
    })
    assert activity.activity_type == "running"
    assert activity.distance_km == 8
    assert activity.average_heart_rate_bpm == 150
