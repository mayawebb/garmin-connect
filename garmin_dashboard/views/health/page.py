"""Health, sleep, and recovery trend page."""

import pandas as pd
import plotly.express as px
import streamlit as st

from garmin_dashboard.config import DATABASE_PATH
from garmin_dashboard.health_metrics import health_trend_rows
from garmin_dashboard.storage import ActivityRepository
from garmin_dashboard.views.common import activity_frame
from garmin_dashboard.views.chat_widget import render_training_chat
from garmin_dashboard.wellness import wellness_metric_points


def main():
    st.title("Health")
    st.caption("Observed heart rate, sleep, activity and recovery signals. No composite recovery score is inferred.")
    repository = ActivityRepository(DATABASE_PATH)
    repository.initialize()
    activities = repository.list_activities()
    snapshots = repository.list_wellness_snapshots()
    points = wellness_metric_points(snapshots)

    rows = health_trend_rows(points, activities)
    health = pd.DataFrame(rows)

    if health.empty:
        st.info("No dated wellness measurements are stored yet. Use **Sync wellness history** in the sidebar.")
    else:
        desired = ["Resting heart rate", "Average heart rate on runs", "Sleep score", "Body Battery"]
        cards = st.columns(4)
        for card, label in zip(cards, desired):
            subset = health[health["Metric"] == label].sort_values("Date")
            if subset.empty:
                card.metric(label, "Unavailable")
            else:
                latest = subset.iloc[-1]
                value = f"{latest['Value']:.0f} {latest['Unit']}" if latest["Unit"] in {"bpm", "score"} else f"{latest['Value']:.1f} {latest['Unit']}"
                card.metric(label, value, help=f"Latest available: {latest['Date']:%Y-%m-%d}")

        selected = st.selectbox("Health metric", sorted(health["Metric"].unique()))
        metric_frame = health[health["Metric"] == selected].sort_values("Date")
        st.plotly_chart(px.line(metric_frame, x="Date", y="Value", markers=True, labels={"Value": metric_frame["Unit"].iloc[0]}), width="stretch", theme=None)
        st.caption(f"{len(metric_frame)} recorded values · {metric_frame['Date'].min():%Y-%m-%d} to {metric_frame['Date'].max():%Y-%m-%d} · missing days are not filled.")

        st.subheader("Recovery signals")
        st.caption("Sleep, HRV, resting heart rate and Body Battery are shown as separate Garmin measurements; this page does not combine them into a made-up score.")
        recovery_metrics = ["Sleep score", "Nightly HRV", "Weekly HRV average", "Resting heart rate", "Body Battery"]
        available = [metric for metric in recovery_metrics if metric in health["Metric"].unique()]
        if available:
            recovery_frame = health[health["Metric"].isin(available)]
            st.dataframe(
                recovery_frame.groupby("Metric").agg(
                    First=("Date", "min"), Last=("Date", "max"), Measurements=("Value", "count"),
                    Latest=("Value", "last"),
                ).reset_index(), hide_index=True, width="stretch",
            )

    st.subheader("VO₂ max")
    vo2_values = []
    for point in points:
        if "vo2max" in point.metric.lower() or "vo2_max" in point.metric.lower():
            vo2_values.append((pd.Timestamp(point.day), point.value))
    for activity in activities:
        vo2_values.extend(_find_vo2(activity.source_fields, activity.started_at))
    if vo2_values:
        vo2_frame = pd.DataFrame([{"Date": item[0], "VO₂ max": item[1]} for item in vo2_values])
        st.plotly_chart(px.line(vo2_frame, x="Date", y="VO₂ max", markers=True), width="stretch", theme=None)
    else:
        st.info("Garmin has not returned a VO₂ max value in the synced records. No value or trend is estimated here.")
        st.markdown("**What can help:** keep a consistent aerobic base, then use a controlled interval session when your recent training is supporting it. Compare a Garmin VO₂ max trend only if the device/API begins returning the metric.")

    st.subheader("Ideas from your trends")
    for observation in _health_observations(health):
        st.markdown(f"- {observation}")

    st.subheader("Activity heart rate")
    activity_frame_data = activity_frame(activities)
    if not activity_frame_data.empty:
        hr_frame = activity_frame_data.dropna(subset=["Avg heart rate (bpm)"])
        if not hr_frame.empty:
            hr_frame = hr_frame[hr_frame["Type"].str.contains("run", case=False, na=False)]
            if not hr_frame.empty:
                st.plotly_chart(px.line(hr_frame, x="Date", y="Avg heart rate (bpm)", markers=True, color="Type"), width="stretch", theme=None)
            else:
                st.info("No run average heart-rate measurements are available.")

    st.subheader("Raw wellness payloads")
    if snapshots:
        source = st.selectbox("Saved data source", sorted({snapshot["source"] for snapshot in snapshots}))
        options = [snapshot for snapshot in snapshots if snapshot["source"] == source]
        index = st.selectbox("Saved date window", range(len(options)), format_func=lambda value: f"{options[value]['start_date']} to {options[value]['end_date']}")
        with st.expander("Inspect Garmin response fields"):
            st.json(options[index]["payload"])
    else:
        st.caption("No wellness payloads are saved yet.")

    render_training_chat(activities, snapshots, repository, current_page="health")


def _find_vo2(value, activity_date):
    found = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if "vo2max" in str(key).lower() or "vo2_max" in str(key).lower():
                try:
                    found.append((pd.Timestamp(activity_date), float(nested)))
                except (TypeError, ValueError):
                    pass
            else:
                found.extend(_find_vo2(nested, activity_date))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_find_vo2(nested, activity_date))
    return found


def _health_observations(health):
    if health.empty:
        return ["Sync wellness history to establish observed baselines before interpreting health trends."]
    notes = []
    steps = health[health["Metric"] == "Steps"].sort_values("Date")["Value"]
    if len(steps) >= 7:
        recent = steps.tail(7).mean()
        notes.append(f"Your latest seven recorded step values average {recent:,.0f} steps. Short walks can be an easy way to raise daily movement if that is a goal.")
    sleep = health[health["Metric"] == "Sleep duration"]["Value"].dropna()
    if len(sleep) >= 7:
        notes.append(f"Your recorded sleep duration averages {sleep.tail(28).mean():.1f} hours over the latest available nights; compare sleep duration and score together over several weeks.")
    hrv = health[health["Metric"] == "Nightly HRV"]["Value"].dropna()
    if len(hrv) >= 7:
        notes.append(f"Your latest nightly HRV readings average {hrv.tail(7).mean():.0f} ms. Compare against your own longer-term baseline rather than a population target.")
    resting = health[health["Metric"] == "Resting heart rate"]["Value"].dropna()
    if len(resting) >= 7:
        notes.append(f"Your recent resting-heart-rate mean is {resting.tail(7).mean():.0f} bpm. Consistent aerobic training and sleep are useful trends to review alongside it; a single reading is not a recovery verdict.")
    return notes or ["There are not yet enough recorded wellness values for trend-based suggestions."]


main()
