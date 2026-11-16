from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

import garmin_dashboard.web as web
from garmin_dashboard.chat import ChartRequest
from garmin_dashboard.models import Activity
from garmin_dashboard.storage import ActivityRepository


def _repository(tmp_path):
    repository = ActivityRepository(tmp_path / "dashboard.sqlite3")
    repository.initialize()
    repository.upsert(Activity(
        activity_id="run-1",
        started_at=datetime(2026, 11, 12, 7, tzinfo=timezone.utc),
        activity_type="running",
        distance_m=5000,
        duration_s=1800,
        average_heart_rate_bpm=150,
    ))
    repository.upsert(Activity(
        activity_id="yoga-1",
        started_at=datetime(2026, 11, 13, 8, tzinfo=timezone.utc),
        activity_type="yoga",
    ))
    repository.upsert(Activity(
        activity_id="treadmill-1",
        started_at=datetime(2026, 11, 14, 6, tzinfo=timezone.utc),
        activity_type="treadmill_running",
        distance_m=4000,
        duration_s=1500,
    ))
    repository.upsert_wellness_snapshot(
        "daily_summaries", date(2026, 11, 12), date(2026, 11, 13),
        {"data": [{"calendarDate": "2026-11-12", "movement": {"steps": {"value": 8123}}}]},
    )
    return repository


def test_dashboard_data_returns_curated_sqlite_records_and_missing_values(tmp_path):
    client = TestClient(web.create_app(repository=_repository(tmp_path)))

    response = client.get("/api/dashboard-data")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "garmin_sqlite"
    assert payload["metadata"]["activity_count"] == 2
    assert payload["metadata"]["date_range"] == {"start": "2026-11-12", "end": "2026-11-13"}
    assert payload["activities"][0]["distance_km"] == 5
    assert payload["activities"][1]["distance_km"] is None
    assert payload["health"][0] == {
        "date": "2026-11-12", "metric": "Steps", "value": 8123.0, "unit": "steps",
    }
    assert "activity_id" not in payload["activities"][0]


def test_chat_uses_current_database_context_and_only_last_eight_messages(tmp_path):
    seen = {}

    def fake_chat(question, allowed_metrics, context, *, model, history):
        seen.update(question=question, allowed_metrics=allowed_metrics, context=context, model=model, history=history)
        return type("Result", (), {"answer": "Keep most runs conversational.", "metric": None,
                                    "chart_type": None, "group_by": None})()

    client = TestClient(web.create_app(repository=_repository(tmp_path), openai_chat=fake_chat))
    history = [{"role": "user", "content": f"question {i}"} for i in range(10)]

    response = client.post("/api/chat", json={"question": "How can I lower my heart rate?", "history": history})

    assert response.status_code == 200
    assert response.json() == {"answer": "Keep most runs conversational.", "chart": None}
    assert len(seen["history"]) == 8
    assert "5.0 km" in seen["context"]
    assert "Treadmill" not in seen["context"]
    assert "health:daily_summaries.movement.steps.value" in seen["allowed_metrics"]


def test_sync_uses_garmin_client_and_reports_activity_and_wellness_results(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "GARMIN_API_KEY", "test-garmin-key")
    created = {}

    class FakeClient:
        def __init__(self, api_key):
            created["api_key"] = api_key

        def iter_activities(self, **kwargs):
            created["activity_start"] = kwargs.get("start_date")
            return iter([{
                "activityId": 2, "startTimeLocal": "2026-11-15T06:00:00",
                "activityTypeDTO": {"typeKey": "running"},
                "distance": 3000, "duration": 1000,
            }])

        def fetch_wellness(self, start_date, end_date):
            created["wellness_range"] = (start_date, end_date)
            return {"daily_summaries": {"data": []}}

        def close(self):
            pass

    client = TestClient(web.create_app(
        repository=_repository(tmp_path), garmin_client_factory=FakeClient,
        openai_chat=lambda *args, **kwargs: None,
    ))

    response = client.post("/api/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["activities"] == {"imported": 1, "skipped": 0, "failed": 0, "errors": []}
    assert payload["wellness"]["failed"] == 0
    assert created["api_key"] == "test-garmin-key"
    assert created["activity_start"] == date(2026, 11, 13)
    assert created["wellness_range"][1] == date.today()


def test_sync_without_garmin_key_returns_safe_unavailable_message(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "GARMIN_API_KEY", None)
    client = TestClient(web.create_app(repository=_repository(tmp_path)))

    response = client.post("/api/sync")

    assert response.status_code == 503
    assert "GARMIN_API_KEY" in response.json()["detail"]
    assert "test-garmin-key" not in response.text


def test_chat_returns_empty_chart_when_no_activity_values_are_recorded(tmp_path):
    repository = ActivityRepository(tmp_path / "empty.sqlite3")
    repository.initialize()
    client = TestClient(web.create_app(
        repository=repository,
        openai_chat=lambda *args, **kwargs: ChartRequest("No recorded distance yet.", "distance_km", "line", "week"),
    ))

    response = client.post("/api/chat", json={"question": "Show weekly distance"})

    assert response.status_code == 200
    assert response.json()["chart"]["rows"] == []


def test_chat_chart_is_built_from_curated_outdoor_run_values(tmp_path):
    client = TestClient(web.create_app(
        repository=_repository(tmp_path),
        openai_chat=lambda *args, **kwargs: ChartRequest("Weekly distance is shown.", "distance_km", "line", "week"),
    ))

    response = client.post("/api/chat", json={"question": "Show weekly distance"})

    assert response.status_code == 200
    chart = response.json()["chart"]
    assert chart["unit"] == "Distance (km)"
    assert chart["rows"] == [{"x": "2026-11-09T00:00:00", "value": 5.0}]
