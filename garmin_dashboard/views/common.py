"""Shared, null-aware data preparation for the Streamlit pages."""

import pandas as pd

from ..analytics import format_pace_min_km, is_running_type, pace_minutes_per_km


def activity_frame(activities):
    rows = []
    for activity in activities:
        source = activity.source_fields
        rows.append({
            "Activity ID": activity.activity_id,
            "Date": pd.Timestamp(activity.started_at),
            "Type": activity.activity_type.replace("_", " ").title(),
            "Distance (km)": activity.distance_km,
            "Duration (min)": activity.duration_s / 60 if activity.duration_s is not None else None,
            "Pace (min/km)": pace_minutes_per_km(activity.distance_km, activity.duration_s)
            if is_running_type(activity.activity_type) else None,
            "Elevation gain (m)": activity.elevation_gain_m,
            "Avg heart rate (bpm)": activity.average_heart_rate_bpm,
            "Total sets": _as_number(source.get("totalSets")),
            "Total reps": _as_number(source.get("totalReps")),
            "Avg power (W)": _as_number(source.get("avgPower")),
            "Training effect": source.get("trainingEffectLabel"),
        })
    return pd.DataFrame(rows).sort_values("Date") if rows else pd.DataFrame()


def _as_number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def activity_context(activities) -> str:
    """Compact activity statistics for the training assistant prompt."""
    frame = activity_frame(activities)
    if frame.empty:
        return "No activity history is available."
    run_frame = frame[frame["Type"].str.contains("run", case=False, na=False) & ~frame["Type"].str.contains("treadmill", case=False, na=False)]
    result = [f"Synced activities: {len(frame)} across {frame['Type'].nunique()} types"]
    if not run_frame.empty:
        result.append(f"Running records: {len(run_frame)}")
        for column in ("Distance (km)", "Duration (min)", "Avg heart rate (bpm)"):
            values = run_frame[column].dropna()
            if not values.empty:
                result.append(f"Run {column}: mean {values.mean():.1f}; latest {values.iloc[-1]:.1f}")
        paces = run_frame["Pace (min/km)"].dropna()
        if not paces.empty:
            result.append(f"Outdoor-run median pace: {format_pace_min_km(paces.median())}; latest recorded pace: {format_pace_min_km(paces.iloc[-1])}")
    for activity_type, group in frame.groupby("Type"):
        result.append(f"{activity_type}: {len(group)} sessions")
    return "; ".join(result)
