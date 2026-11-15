import pytest

from garmin_dashboard.chat import ChatError, parse_training_plan
from garmin_dashboard.storage import ActivityRepository


def sample_plan():
    return {
        "title": "Steady 10K build",
        "goal": "Improve 10K time",
        "duration_weeks": 2,
        "weeks": [
            {"week": 1, "focus": "Build consistency", "sessions": [
                {"day": "Tuesday", "activity": "easy_run", "details": "Easy conversational run."},
                {"day": "Saturday", "activity": "strength", "details": "Moderate full-body strength."},
            ]},
            {"week": 2, "focus": "Repeat and review", "sessions": [
                {"day": "Tuesday", "activity": "easy_run", "details": "Repeat the previous easy run."},
                {"day": "Saturday", "activity": "strength", "details": "Repeat with good form."},
            ]},
        ],
        "recovery_notes": "Keep rest days between harder sessions.",
    }


def test_training_plan_parser_accepts_structured_schedule():
    plan = parse_training_plan(sample_plan())
    assert plan.title == "Steady 10K build"
    assert plan.duration_weeks == 2
    assert len(plan.weeks) == 2


def test_training_plan_parser_rejects_missing_weeks_and_unsafe_length():
    payload = sample_plan()
    payload["weeks"] = payload["weeks"][:1]
    with pytest.raises(ChatError):
        parse_training_plan(payload)


def test_repository_persists_and_lists_training_plans(tmp_path):
    repository = ActivityRepository(tmp_path / "plans.sqlite3")
    repository.initialize()
    plan_id = repository.save_training_plan("Train for 10K", sample_plan())
    saved = repository.list_training_plans()
    assert saved[0]["plan_id"] == plan_id
    assert saved[0]["prompt"] == "Train for 10K"
    assert saved[0]["plan"]["title"] == "Steady 10K build"
