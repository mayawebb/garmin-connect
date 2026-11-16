"""Private same-origin API and static dashboard server."""

from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .chat import ChatError, ChartRequest, ask_openai
from .chat_context import (
    ACTIVITY_METRICS,
    HEALTH_PREFIX,
    activity_chart_frame,
    health_chart_frame,
    training_context,
)
from .config import DATABASE_PATH, GARMIN_API_KEY, OPENAI_API_KEY, OPENAI_MODEL, PROJECT_ROOT
from .garmin_client import GarminClient
from .health_metrics import SERIES, health_trend_rows
from .importer import sync_activities
from .static_export import build_static_export
from .storage import ActivityRepository
from .wellness import sync_wellness, wellness_metric_points


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=1200)


class ChatBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=32)


def create_app(
    repository: ActivityRepository | None = None,
    garmin_client_factory=None,
    openai_chat=None,
) -> FastAPI:
    """Create the app with injectable services for tests and local operation."""
    repo = repository or ActivityRepository(DATABASE_PATH)
    repo.initialize()
    client_factory = garmin_client_factory or GarminClient
    chat_function = openai_chat or ask_openai
    uses_real_openai = openai_chat is None

    app = FastAPI(title="Private Garmin Dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.repository = repo

    @app.get("/api/dashboard-data")
    def dashboard_data():
        activities = repo.list_activities()
        points = wellness_metric_points(repo.list_wellness_snapshots())
        return build_static_export(activities, health_trend_rows(points, activities))

    @app.post("/api/chat")
    def chat(body: ChatBody):
        question = body.question.strip()
        if not question:
            raise HTTPException(status_code=422, detail="Question cannot be blank")
        if uses_real_openai and not OPENAI_API_KEY:
            raise HTTPException(status_code=503, detail="OpenAI chat is unavailable. Add OPENAI_API_KEY to the local .env file.")

        activities = repo.list_activities()
        dashboard_activities = [activity for activity in activities if "treadmill" not in activity.activity_type.casefold()]
        points = wellness_metric_points(repo.list_wellness_snapshots())
        allowed_metrics = set(ACTIVITY_METRICS) | {
            HEALTH_PREFIX + point.metric for point in points
        }
        history = [{"role": item.role, "content": item.content} for item in body.history[-8:]]
        try:
            result = chat_function(
                question,
                allowed_metrics,
                training_context(activities, points),
                model=OPENAI_MODEL,
                history=history,
            )
        except ChatError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        chart = None
        if result.metric:
            request = ChartRequest(result.answer, result.metric, result.chart_type, result.group_by)
            if result.metric.startswith(HEALTH_PREFIX):
                frame = health_chart_frame(points, request)
                value_column = "Value"
                x_column = "Period" if result.group_by in {"week", "month"} else "Date"
            else:
                frame = activity_chart_frame(dashboard_activities, request)
                value_column = ACTIVITY_METRICS.get(result.metric, "")
                x_column = {"week": "Period", "month": "Period", "activity_type": "Type", "none": "Date"}.get(result.group_by, "Date")
            rows = []
            if not frame.empty:
                for row in frame.to_dict(orient="records"):
                    x_value = row.get(x_column)
                    rows.append({
                        "x": x_value.isoformat() if hasattr(x_value, "isoformat") else str(x_value),
                        "value": float(row[value_column]),
                    })
            metric_id = result.metric.removeprefix(HEALTH_PREFIX)
            health_unit = next((unit for _label, (metric_path, _factor, unit) in SERIES.items() if metric_path == metric_id), "recorded value")
            chart = {
                "metric": result.metric,
                "chart_type": result.chart_type,
                "group_by": result.group_by,
                "unit": ACTIVITY_METRICS.get(result.metric, health_unit),
                "rows": rows,
            }
        return {"answer": result.answer, "chart": chart}

    @app.post("/api/sync")
    def sync():
        if not GARMIN_API_KEY:
            raise HTTPException(status_code=503, detail="Garmin sync is unavailable. Add GARMIN_API_KEY to the local .env file.")
        try:
            client = client_factory(GARMIN_API_KEY)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Garmin sync unavailable ({type(exc).__name__})") from exc
        try:
            activity_report = sync_activities(client, repo)
            snapshots = repo.list_wellness_snapshots()
            if snapshots:
                last_snapshot_day = max(item["end_date"] for item in snapshots)
                wellness_start = max(last_snapshot_day - timedelta(days=6), date.min)
            else:
                earliest_activity = min((item.started_at.date() for item in repo.list_activities()), default=None)
                wellness_start = earliest_activity or (date.today() - timedelta(days=365))
            wellness_report = sync_wellness(client, repo, wellness_start, date.today())
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Garmin sync unavailable ({type(exc).__name__})") from exc
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        return {
            "activities": _report_payload(activity_report),
            "wellness": _report_payload(wellness_report),
        }

    app.mount("/", StaticFiles(directory=Path(PROJECT_ROOT) / "static_site", html=True), name="dashboard")
    return app


def _report_payload(report) -> dict:
    return {
        "imported": report.imported,
        "skipped": report.skipped,
        "failed": report.failed,
        "errors": list(report.errors),
    }


app = create_app()
