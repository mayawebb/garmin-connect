"""Compact, data-grounded context shared by Streamlit and the private web API."""

import pandas as pd

from .analytics import predicted_5k_trend
from .views.common import activity_context


ACTIVITY_METRICS = {
    "distance_km": "Distance (km)",
    "pace_min_km": "Pace (min/km)",
    "duration_min": "Duration (min)",
    "elevation_gain_m": "Elevation gain (m)",
    "average_heart_rate_bpm": "Avg heart rate (bpm)",
    "activity_count": "Activity count",
}
HEALTH_PREFIX = "health:"


def training_context(activities, points) -> str:
    """Summarize only recorded measures and derived trends for the model."""
    activities = [activity for activity in activities if "treadmill" not in activity.activity_type.casefold()]
    lines = [activity_context(activities)]
    predictions = predicted_5k_trend(activities)
    if predictions:
        best = min(predictions, key=lambda row: row["predicted_5k_seconds"])
        minutes, seconds = divmod(round(best["predicted_5k_seconds"]), 60)
        lines.append(
            f"Best recorded-effort 5K estimate: {minutes}:{seconds:02d}, derived from "
            f"a {best['source_distance_km']:.1f} km outdoor activity on {best['date']:%Y-%m-%d} "
            "using Riegel exponent 1.06; not a guaranteed race result."
        )
    else:
        lines.append("5K estimate unavailable: no outdoor run of at least 2 km has both distance and duration.")

    if points:
        health_ids = sorted({point.metric for point in points})
        lines.append("Available health metric IDs for chart requests: " + ", ".join(HEALTH_PREFIX + metric for metric in health_ids))
        latest_by_metric = {}
        for point in points:
            latest_by_metric.setdefault(point.metric, []).append(point)
        health = []
        for metric, rows in latest_by_metric.items():
            rows.sort(key=lambda item: item.day)
            recent = rows[-28:]
            health.append(f"{metric}: latest {rows[-1].value:g} on {rows[-1].day}; 28 recorded-point mean {sum(p.value for p in recent) / len(recent):.2f}")
        lines.append("Health values: " + "; ".join(health[:40]))
    else:
        lines.append("No synced wellness values are available; health metrics are unknown.")
    lines.append("Activity chart metric IDs: " + ", ".join(f"{key} ({value})" for key, value in ACTIVITY_METRICS.items()))
    return "\n".join(lines)[:8000]


def activity_chart_frame(activities, chart_request):
    """Build an activity chart frame from fixed columns and a validated request."""
    from .chat import build_chart_data
    from .views.common import activity_frame

    frame = activity_frame(activities)
    if frame.empty:
        return frame
    frame["Date"] = pd.to_datetime(frame["Date"].map(
        lambda value: value.tz_localize(None) if getattr(value, "tzinfo", None) else value
    ))
    return build_chart_data(frame, chart_request)


def health_chart_frame(points, chart_request):
    """Build a health chart frame for a validated health metric request."""
    metric = chart_request.metric.removeprefix(HEALTH_PREFIX)
    frame = pd.DataFrame([
        {"Date": pd.Timestamp(point.day), "Value": point.value}
        for point in points if point.metric == metric
    ])
    if frame.empty or chart_request.group_by == "activity_type":
        return pd.DataFrame()
    if chart_request.group_by in {"week", "month"}:
        rule = "W-SUN" if chart_request.group_by == "week" else "M"
        frame["Period"] = frame["Date"].dt.to_period(rule).dt.start_time
        frame = frame.groupby("Period", as_index=False)["Value"].mean()
    return frame.sort_values("Date" if "Date" in frame else "Period")
