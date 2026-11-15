from datetime import date

from garmin_dashboard.storage import ActivityRepository
from garmin_dashboard.wellness import sync_wellness, wellness_metric_points


def test_wellness_sync_persists_raw_payloads_by_endpoint_and_date_range(tmp_path):
    class Client:
        def fetch_wellness(self, start_date, end_date):
            assert start_date == date(2026, 1, 1)
            assert end_date == date(2026, 1, 2)
            return {
                "daily_summaries": {"data": [{"calendarDate": "2026-01-01", "heartRate": {"restingHeartRate": 51}}]},
                "sleep_summaries": [{"calendarDate": "2026-01-01", "sleepScore": 86}],
                "hrv_summaries": [{"calendarDate": "2026-01-01", "weeklyAvg": 48}],
            }

    repository = ActivityRepository(tmp_path / "activities.sqlite3")

    report = sync_wellness(Client(), repository, date(2026, 1, 1), date(2026, 1, 2))
    snapshots = repository.list_wellness_snapshots()

    assert report.imported == 3
    assert report.skipped == 0
    assert {snapshot["source"] for snapshot in snapshots} == {"daily_summaries", "sleep_summaries", "hrv_summaries"}
    assert snapshots[0]["start_date"] == date(2026, 1, 1)


def test_wellness_chart_points_use_only_present_numeric_values():
    points = wellness_metric_points([
        {
            "source": "sleep_summaries",
            "payload": [{"calendarDate": "2026-01-01", "sleepScore": 86, "sleepTimeSeconds": 28800}],
        },
        {
            "source": "daily_summaries",
            "payload": {"data": [
                {"calendarDate": "2026-01-01", "heartRate": {"restingHeartRate": 51}},
                {"calendarDate": "2026-01-02", "heartRate": {"restingHeartRate": None}},
            ]},
        },
    ])

    assert {point.metric for point in points} == {
        "sleep_summaries.sleepScore",
        "sleep_summaries.sleepTimeSeconds",
        "daily_summaries.heartRate.restingHeartRate",
    }
    assert not any(point.day == date(2026, 1, 2) for point in points)


def test_wellness_sync_chunks_long_ranges_and_saves_each_payload(tmp_path):
    calls = []

    class Client:
        def fetch_wellness(self, start_date, end_date):
            calls.append((start_date, end_date))
            return {"daily_summaries": [{"calendarDate": start_date.isoformat(), "stepCount": 100}]}

    repository = ActivityRepository(tmp_path / "wellness.sqlite3")
    report = sync_wellness(Client(), repository, date(2026, 1, 1), date(2026, 3, 7))

    assert calls == [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 7)),
    ]
    assert report.imported == 3
    assert len(repository.list_wellness_snapshots()) == 3


def test_hrv_summary_wrapper_is_flattened_by_date():
    points = wellness_metric_points([{
        "source": "hrv_summaries",
        "payload": {
            "userProfilePk": 1,
            "hrvSummaries": [
                {"calendarDate": "2026-01-01", "hrvSummary": {"lastNightAvg": 48, "weeklyAvg": 52}},
                {"calendarDate": "2026-01-02", "hrvSummary": {"lastNightAvg": None}},
            ],
        },
    }])
    assert [(point.day, point.metric, point.value) for point in points] == [
        (date(2026, 1, 1), "hrv_summaries.hrvSummary.lastNightAvg", 48),
        (date(2026, 1, 1), "hrv_summaries.hrvSummary.weeklyAvg", 52),
    ]
