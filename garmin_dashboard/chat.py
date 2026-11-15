"""OpenAI-powered chat, constrained to validated activity chart requests."""

from dataclasses import dataclass
import json

import requests


class ChatError(ValueError):
    """The OpenAI request failed or returned an unsupported response."""


@dataclass(frozen=True)
class ChartRequest:
    answer: str
    metric: str | None
    chart_type: str | None
    group_by: str | None


CHART_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "chart": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "properties": {
                        "metric": {"type": "string"},
                        "chart_type": {"type": "string", "enum": ["line", "bar"]},
                        "group_by": {"type": "string", "enum": ["week", "month", "activity_type", "none"]},
                    },
                    "required": ["metric", "chart_type", "group_by"],
                    "additionalProperties": False,
                },
            ],
        },
    },
    "required": ["answer", "chart"],
    "additionalProperties": False,
}


def parse_chart_request(payload: dict, allowed_metrics: set[str]) -> ChartRequest:
    if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str):
        raise ChatError("OpenAI returned an invalid response")
    chart = payload.get("chart")
    if chart is None:
        return ChartRequest(payload["answer"], None, None, None)
    if not isinstance(chart, dict):
        raise ChatError("OpenAI returned an invalid chart request")
    metric, chart_type, group_by = chart.get("metric"), chart.get("chart_type"), chart.get("group_by")
    if metric not in allowed_metrics:
        raise ChatError("Requested metric is unavailable or unsupported")
    if chart_type not in {"line", "bar"} or group_by not in {"week", "month", "activity_type", "none"}:
        raise ChatError("Requested chart format is unsupported")
    return ChartRequest(payload["answer"], metric, chart_type, group_by)


def ask_openai(
    question: str,
    allowed_metrics: set[str],
    context: str,
    *,
    model: str = "gpt-5.4-mini",
    history: list[dict[str, str]] | None = None,
    timeout: int = 60,
    api_key: str | None = None,
    post=requests.post,
) -> ChartRequest:
    """Ask OpenAI about a compact training summary and optional chart spec."""
    messages = []
    for item in (history or [])[-8:]:
        if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
            messages.append({"role": item["role"], "content": item["content"][:1200]})
    messages.append({"role": "user", "content": (
        f"Available metric IDs: {sorted(allowed_metrics)}\n"
        f"Training and wellness summary: {context[:8000]}\nQuestion: {question[:2000]}"
    )})
    try:
        key = api_key or _openai_api_key()
        response = post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "instructions": (
                "You are a concise personal training-data assistant. Use only the supplied data summary; "
                "state when a requested value is missing. Never invent metrics, claim causation, or provide a medical diagnosis. "
                "Return the required JSON. Set chart to null unless the user asks for a visualization. "
                "Chart metrics must exactly match an available metric ID; never return code or SQL."
                ),
                "input": messages,
                "text": {"format": {"type": "json_schema", "name": "training_chat", "schema": CHART_SCHEMA, "strict": True}},
                "store": False,
                "max_output_tokens": 1200,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = json.loads(_response_output_text(response.json()))
    except ChatError:
        raise
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        detail = _api_error_detail(status, "chat")
        raise ChatError(f"OpenAI chat unavailable ({detail})") from exc
    except Exception as exc:
        raise ChatError(f"OpenAI chat unavailable or returned invalid data ({type(exc).__name__})") from exc
    return parse_chart_request(payload, allowed_metrics)


def build_chart_data(frame, request: ChartRequest):
    """Build chart rows from fixed activity columns; never evaluates model output."""
    import pandas as pd

    source_columns = {
        "distance_km": "Distance (km)",
        "pace_min_km": "Pace (min/km)",
        "duration_min": "Duration (min)",
        "elevation_gain_m": "Elevation gain (m)",
        "average_heart_rate_bpm": "Avg heart rate (bpm)",
    }
    if request.metric == "activity_count":
        values = frame.copy()
        values["Activity count"] = 1
        value_column = "Activity count"
    elif request.metric in source_columns:
        value_column = source_columns[request.metric]
        values = frame.dropna(subset=[value_column]).copy()
    else:
        raise ChatError("Requested metric is unavailable")
    if values.empty:
        return values
    if request.group_by == "none":
        columns = ["Date", "Type", value_column]
        return values[columns].sort_values("Date")
    if request.group_by == "activity_type":
        groups = ["Type"]
    elif request.group_by in {"week", "month"}:
        values["Period"] = values["Date"].dt.to_period("W-SUN" if request.group_by == "week" else "M").dt.start_time
        groups = ["Period"]
    else:
        raise ChatError("Requested grouping is unsupported")
    aggregation = "sum" if request.metric in {"distance_km", "duration_min", "elevation_gain_m", "activity_count"} else "mean"
    return values.groupby(groups, as_index=False)[value_column].agg(aggregation).sort_values(groups)


@dataclass(frozen=True)
class TrainingPlan:
    title: str
    goal: str
    duration_weeks: int
    weeks: list[dict]
    recovery_notes: str

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "goal": self.goal,
            "duration_weeks": self.duration_weeks,
            "weeks": self.weeks,
            "recovery_notes": self.recovery_notes,
        }


TRAINING_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "goal": {"type": "string"},
        "duration_weeks": {"type": "integer"},
        "weeks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "week": {"type": "integer"},
                    "focus": {"type": "string"},
                    "sessions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "day": {"type": "string"},
                                "activity": {"type": "string"},
                                "details": {"type": "string"},
                            },
                            "required": ["day", "activity", "details"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["week", "focus", "sessions"],
                "additionalProperties": False,
            },
        },
        "recovery_notes": {"type": "string"},
    },
    "required": ["title", "goal", "duration_weeks", "weeks", "recovery_notes"],
    "additionalProperties": False,
}


def parse_training_plan(payload: dict) -> TrainingPlan:
    if not isinstance(payload, dict):
        raise ChatError("OpenAI returned an invalid training plan")
    title, goal = payload.get("title"), payload.get("goal")
    duration, weeks, recovery = payload.get("duration_weeks"), payload.get("weeks"), payload.get("recovery_notes")
    if not isinstance(title, str) or not title.strip() or not isinstance(goal, str) or not goal.strip():
        raise ChatError("Training plan needs a title and goal")
    if not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= 24:
        raise ChatError("Training plan duration must be between 1 and 24 weeks")
    if not isinstance(weeks, list) or len(weeks) != duration or not isinstance(recovery, str):
        raise ChatError("Training plan must include one valid schedule for every week")
    allowed_activity = {
        "easy_run", "intervals", "tempo", "long_run", "strength", "cardio",
        "yoga", "rest", "recovery", "race_pace", "mobility", "other",
    }
    clean_weeks = []
    for expected_week, week in enumerate(weeks, start=1):
        if not isinstance(week, dict) or week.get("week") != expected_week:
            raise ChatError("Training plan weeks must be numbered in order")
        if not isinstance(week.get("focus"), str) or not isinstance(week.get("sessions"), list):
            raise ChatError("Training plan week is missing its focus or sessions")
        if not 1 <= len(week["sessions"]) <= 7:
            raise ChatError("Each week must contain between 1 and 7 sessions")
        sessions = []
        for session in week["sessions"]:
            if not isinstance(session, dict):
                raise ChatError("Training plan session is invalid")
            day, activity, details = session.get("day"), session.get("activity"), session.get("details")
            if not all(isinstance(value, str) and value.strip() for value in (day, details)):
                raise ChatError("Training plan session needs a day and description")
            if activity not in allowed_activity:
                raise ChatError("Training plan contains an unsupported session type")
            sessions.append({"day": day.strip(), "activity": activity, "details": details.strip()[:600]})
        clean_weeks.append({"week": expected_week, "focus": week["focus"].strip(), "sessions": sessions})
    return TrainingPlan(title.strip()[:120], goal.strip()[:300], duration, clean_weeks, recovery.strip()[:1000])


def generate_training_plan(
    question: str,
    context: str,
    *,
    history: list[dict[str, str]] | None = None,
    model: str = "gpt-5.4-mini",
    timeout: int = 120,
    api_key: str | None = None,
    post=requests.post,
) -> TrainingPlan:
    """Generate and validate a data-aware plan; never execute model output."""
    messages = []
    for item in (history or [])[-8:]:
        if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
            messages.append({"role": item["role"], "content": item["content"][:1200]})
    messages.append({"role": "user", "content": f"Training summary: {context[:8000]}\nGoal/request: {question[:2000]}"})
    try:
        key = api_key or _openai_api_key()
        response = post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "instructions": (
                "Create a practical, conservative personal training plan using only the supplied training summary. "
                "Include rest/recovery. Do not diagnose, prescribe supplements, or tell the user to train through pain. "
                "Treat missing metrics as unknown. Return only the required JSON structure."
                ),
                "input": messages,
                "text": {"format": {"type": "json_schema", "name": "training_plan", "schema": TRAINING_PLAN_SCHEMA, "strict": True}},
                "store": False,
                "max_output_tokens": 5000,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = json.loads(_response_output_text(response.json()))
    except ChatError:
        raise
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        detail = _api_error_detail(status, "plan generation")
        raise ChatError(f"OpenAI plan generation unavailable ({detail})") from exc
    except Exception as exc:
        raise ChatError(f"OpenAI plan generation failed ({type(exc).__name__})") from exc
    return parse_training_plan(payload)


def _openai_api_key():
    from .config import OPENAI_API_KEY

    if not OPENAI_API_KEY:
        raise ChatError("Set OPENAI_API_KEY in your local .env file")
    return OPENAI_API_KEY


def _response_output_text(payload: dict) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks = []
    for item in payload.get("output", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if not chunks:
        raise ValueError("OpenAI response has no output text")
    return "".join(chunks)


def _api_error_detail(status: int | None, operation: str) -> str:
    if status == 401:
        return "HTTP 401: check OPENAI_API_KEY"
    if status == 429:
        return "HTTP 429: check API usage limits or billing"
    if status == 403:
        return "HTTP 403: check model access for the API project"
    return f"HTTP {status}" if status is not None else f"network {operation} error"
