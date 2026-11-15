import pytest

from garmin_dashboard.chat import ChartRequest, ChatError, parse_chart_request


def test_chart_request_allows_only_known_metrics_and_chart_types():
    request = parse_chart_request({
        "answer": "Your weekly distance is shown below.",
        "chart": {"metric": "distance_km", "chart_type": "line", "group_by": "week"},
    }, {"distance_km", "pace_min_km"})
    assert request == ChartRequest("Your weekly distance is shown below.", "distance_km", "line", "week")


def test_chart_request_rejects_unknown_metrics_and_executable_content():
    with pytest.raises(ChatError):
        parse_chart_request({"answer": "x", "chart": {"metric": "__import__('os')", "chart_type": "line", "group_by": "week"}}, {"distance_km"})


def test_build_chart_data_aggregates_only_present_activity_metrics():
    import pandas as pd
    from garmin_dashboard.chat import build_chart_data

    frame = pd.DataFrame({
        "Date": pd.to_datetime(["2026-01-02", "2026-01-03", "2026-02-02"]),
        "Type": ["Running", "Running", "Cycling"],
        "Distance (km)": [5.0, None, 20.0],
        "Pace (min/km)": [5.0, None, None],
    })
    result = build_chart_data(frame, ChartRequest("", "distance_km", "bar", "month"))
    assert result["Distance (km)"].tolist() == [5.0, 20.0]
    assert len(result) == 2
