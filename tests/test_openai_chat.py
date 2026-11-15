import json
import pytest

from garmin_dashboard.chat import ChatError, ask_openai, generate_training_plan


class FakeResponse:
    def __init__(self, output_text):
        self.output_text = output_text

    def raise_for_status(self):
        pass

    def json(self):
        return {"output": [{"type": "message", "content": [{"type": "output_text", "text": self.output_text}]}]}


def test_openai_chat_uses_provided_context_and_parses_allowlisted_chart():
    seen = {}
    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(json.dumps({
        "answer": "Your recorded weekly totals are shown below.",
        "chart": {"metric": "distance_km", "chart_type": "line", "group_by": "week"},
        }))
    result = ask_openai("Show my weekly distance", {"distance_km"}, "weekly data", api_key="test-key", post=post)
    assert result.metric == "distance_km"
    assert seen["url"] == "https://api.openai.com/v1/responses"
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert "weekly data" in str(seen["json"]["input"])
    assert seen["json"]["store"] is False
    assert seen["json"]["text"]["format"]["type"] == "json_schema"


def test_openai_chat_rejects_unavailable_chart_metrics():
    def post(url, **kwargs):
        return FakeResponse(json.dumps({
        "answer": "Chart",
        "chart": {"metric": "sleep_score", "chart_type": "line", "group_by": "week"},
        }))
    with pytest.raises(ChatError, match="unavailable"):
        ask_openai("Chart sleep", {"distance_km"}, "", api_key="test-key", post=post)


def test_plan_generation_uses_openai_responses_and_validates_schedule():
    plan_payload = {
        "title": "10K build", "goal": "Improve 10K", "duration_weeks": 1,
        "weeks": [{"week": 1, "focus": "Base", "sessions": [
            {"day": "Monday", "activity": "easy_run", "details": "Easy conversational run."},
        ]}],
        "recovery_notes": "Take rest as needed.",
    }
    seen = {}
    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(json.dumps(plan_payload))
    result = generate_training_plan("Plan for a 10K", "2 runs weekly", api_key="test-key", post=post)
    assert result.title == "10K build"
    assert seen["json"]["store"] is False
