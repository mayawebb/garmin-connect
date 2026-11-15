from datetime import datetime, timezone

from garmin_dashboard.activity_streams import ActivityStreamPoint, parse_record_messages, sync_activity_streams
from garmin_dashboard.models import Activity
from garmin_dashboard.storage import ActivityRepository


def test_record_messages_keep_available_sensor_fields_and_missing_values():
    messages = {"record_mesgs": [
        {
            "timestamp": {"field_value": datetime(2026, 1, 1, tzinfo=timezone.utc)},
            "heart_rate": {"field_value": 145},
            "distance": {"field_value": 1000.0},
            "speed": {"field_value": 3.2},
        },
        {"timestamp": {"field_value": datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)}},
    ]}

    points = parse_record_messages(messages)

    assert points == [
        ActivityStreamPoint(datetime(2026, 1, 1, tzinfo=timezone.utc), 145, 1000.0, 3.2, None, None),
        ActivityStreamPoint(datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc), None, None, None, None, None),
    ]


def test_zero_speed_and_altitude_are_preserved():
    point = parse_record_messages({"record_mesgs": [{
        "enhanced_speed": {"field_value": 0},
        "enhanced_altitude": {"field_value": 0},
    }]})[0]

    assert point.speed_mps == 0
    assert point.altitude_m == 0


def test_activity_zip_parser_selects_fit_entry_and_passes_it_to_decoder(monkeypatch):
    from io import BytesIO
    import zipfile
    import garmin_dashboard.activity_streams as streams

    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("activity.fit", b"fit-content")
    monkeypatch.setattr(streams, "read_fit_messages", lambda content: {
        "record_mesgs": [{"heart_rate": {"field_value": 144}}]
    })

    points = streams.parse_activity_zip(archive.getvalue())

    assert points[0].heart_rate_bpm == 144


def test_imported_fit_file_is_cached_and_not_downloaded_twice(tmp_path, monkeypatch):
    import garmin_dashboard.activity_streams as streams

    monkeypatch.setattr(streams, "parse_activity_zip", lambda _content: [
        ActivityStreamPoint(datetime(2026, 1, 1, tzinfo=timezone.utc), 145, 1000, None, None, None)
    ])

    class Client:
        def __init__(self):
            self.downloads = []

        def download_activity(self, activity_id):
            self.downloads.append(activity_id)
            return b"zip-data"

    repository = ActivityRepository(tmp_path / "activities.sqlite3")
    repository.initialize()
    repository.upsert(Activity(
        activity_id="42",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        activity_type="running",
    ))
    client = Client()

    first_report = sync_activity_streams(client, repository)
    second_report = sync_activity_streams(client, repository)

    assert first_report.imported == 1
    assert second_report.skipped == 1
    assert client.downloads == ["42"]
    assert repository.get_activity_stream("42")[0]["heart_rate_bpm"] == 145
