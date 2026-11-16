"""Health, sleep, and recovery trend page."""

from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from garmin_dashboard.analytics import format_pace_min_km
from garmin_dashboard.config import DATABASE_PATH
from garmin_dashboard.health_metrics import health_trend_rows, sleep_run_association
from garmin_dashboard.storage import ActivityRepository
from garmin_dashboard.views.common import activity_frame
from garmin_dashboard.views.chat_widget import render_training_chat
from garmin_dashboard.wellness import wellness_metric_points


def main():
    st.title("Health")
    st.caption("What changed in sleep, recovery signals, and run effort. Each measure stays separate; no made-up readiness score.")
    repository = ActivityRepository(DATABASE_PATH)
    repository.initialize()
    activities = repository.list_activities()
    snapshots = repository.list_wellness_snapshots()
    points = wellness_metric_points(snapshots)

    rows = health_trend_rows(points, activities)
    health = pd.DataFrame(rows)
    if not health.empty:
        health["Date"] = pd.to_datetime(health["Date"])
    wellness_end = max((pd.Timestamp(point.day) for point in points), default=None)

    if health.empty:
        st.info("No dated wellness measurements are stored yet. Use **Sync wellness history** in the sidebar.")
    else:
        st.subheader("Recovery snapshot")
        if wellness_end is not None:
            st.caption(f"Seven-day averages through {wellness_end:%b %-d, %Y}; change is compared with the previous seven calendar days. Missing days are not filled.")
        else:
            st.caption("No wellness dates are available yet. Run heart-rate records can still be viewed below.")
        recovery_metrics = ["Sleep duration", "Sleep score", "Resting heart rate", "Nightly HRV", "Body Battery", "Steps"]
        first_row = st.columns(4)
        second_row = st.columns(2)
        cards = first_row + second_row
        for card, metric in zip(cards, recovery_metrics):
            _render_recovery_card(card, health, metric, wellness_end)
        st.info(_recovery_story(health, wellness_end))

        st.subheader("Health trends")
        health_window = st.selectbox("Trend window", ["Last 12 weeks", "Last 6 months", "All history"], index=1, key="health_window")
        selected = st.selectbox("Measure", sorted(health["Metric"].unique()))
        metric_frame = health[health["Metric"] == selected].sort_values("Date")
        metric_frame = metric_frame.groupby("Date", as_index=False).agg(Value=("Value", "median"), readings=("Value", "size"))
        metric_latest = metric_frame["Date"].max()
        metric_frame["rolling_7_day"] = metric_frame.set_index("Date")["Value"].rolling("7D", min_periods=3).mean().to_numpy()
        metric_frame = _filter_date_window(metric_frame, health_window, metric_latest)
        unit = health.loc[health["Metric"] == selected, "Unit"].iloc[0]
        metric_figure = go.Figure()
        metric_figure.add_scatter(
            x=metric_frame["Date"], y=metric_frame["Value"], mode="markers", name="Recorded values",
            marker={"size": 5, "color": "#84948C", "opacity": 0.45}, customdata=metric_frame["readings"],
            hovertemplate="%{x|%b %-d, %Y}<br>%{y:.1f} " + unit + "<br>%{customdata} reading(s)<extra></extra>",
        )
        metric_figure.add_scatter(
            x=metric_frame["Date"], y=metric_frame["rolling_7_day"], mode="lines", name="7-day average",
            line={"color": "#70C3A2", "width": 3}, hovertemplate="7-day average: %{y:.1f} " + unit + "<extra></extra>",
        )
        metric_figure.update_layout(xaxis_title="Date", yaxis_title=unit, hovermode="x unified", legend_title_text="")
        st.plotly_chart(metric_figure, width="stretch", theme=None)
        st.caption(f"{selected}: {len(metric_frame)} daily dates in this view. Points are actual recorded values; the line smooths seven calendar days and requires three readings. Gaps remain gaps.")

        st.subheader("Does sleep score track with run effort?")
        association = sleep_run_association(activities, points)
        if association and association["groups"]["Above median"]["run_count"] and association["groups"]["At or below median"]["run_count"]:
            at_or_below = association["groups"]["At or below median"]
            above = association["groups"]["Above median"]
            left, right = st.columns(2)
            left.metric(
                f"Sleep score ≤ {association['sleep_score_median']:.0f} · {at_or_below['run_count']} runs",
                format_pace_min_km(at_or_below["median_pace_min_km"]),
                delta=f"Median run HR {at_or_below['median_heart_rate_bpm']:.0f} bpm",
                delta_color="off",
            )
            right.metric(
                f"Sleep score > {association['sleep_score_median']:.0f} · {above['run_count']} runs",
                format_pace_min_km(above["median_pace_min_km"]),
                delta=f"Median run HR {above['median_heart_rate_bpm']:.0f} bpm",
                delta_color="off",
            )
            pace_delta_s = round((above["median_pace_min_km"] - at_or_below["median_pace_min_km"]) * 60)
            hr_delta = above["median_heart_rate_bpm"] - at_or_below["median_heart_rate_bpm"]
            pace_phrase = f"{abs(pace_delta_s)} sec/km slower" if pace_delta_s > 0 else f"{abs(pace_delta_s)} sec/km faster" if pace_delta_s < 0 else "the same pace"
            hr_phrase = f"{abs(hr_delta):.0f} bpm higher" if hr_delta > 0 else f"{abs(hr_delta):.0f} bpm lower" if hr_delta < 0 else "the same median heart rate"
            st.caption(
                f"Among {association['matched_run_count']} outdoor runs with both same-date sleep scores and run effort, "
                f"runs above the matched-run median sleep score were {pace_phrase} with {hr_phrase}. "
                "This is a same-calendar-date association, not proof that sleep caused the workout result; run type, route, and weather vary."
            )
        else:
            st.info("There are not enough outdoor runs with both same-date sleep scores and pace/heart-rate values to compare.")

    st.subheader("VO₂ max")
    vo2_values = []
    for point in points:
        if "vo2max" in point.metric.lower() or "vo2_max" in point.metric.lower():
            vo2_values.append((pd.Timestamp(point.day), point.value))
    for activity in activities:
        vo2_values.extend(_find_vo2(activity.source_fields, activity.started_at))
    if vo2_values:
        vo2_frame = pd.DataFrame([{"Date": pd.Timestamp(item[0]), "VO₂ max": item[1]} for item in vo2_values]).sort_values("Date")
        st.plotly_chart(px.line(vo2_frame, x="Date", y="VO₂ max", markers=True), width="stretch", theme=None)
    else:
        st.info("No VO₂ max values were returned in the synced Garmin data, so this dashboard cannot show or evaluate a VO₂ max trend. It does not estimate a replacement value.")

    st.subheader("Run heart-rate trend")
    activity_frame_data = activity_frame(activities)
    if not activity_frame_data.empty:
        hr_frame = activity_frame_data.dropna(subset=["Avg heart rate (bpm)"])
        if not hr_frame.empty:
            hr_frame = hr_frame[
                hr_frame["Type"].str.contains("run", case=False, na=False)
                & ~hr_frame["Type"].str.contains("treadmill", case=False, na=False)
            ].copy()
            if not hr_frame.empty:
                hr_frame["Week"] = hr_frame["Date"].dt.to_period("W-SUN").dt.start_time
                weekly_hr = hr_frame.groupby("Week", as_index=False).agg(
                    median_hr=("Avg heart rate (bpm)", "median"), runs=("Activity ID", "count"),
                ).sort_values("Week")
                weekly_hr["rolling_hr"] = weekly_hr["median_hr"].rolling(4, min_periods=2).median()
                hr_latest = weekly_hr["Week"].max()
                weekly_hr = _filter_date_window(weekly_hr.rename(columns={"Week": "Date"}), health_window if not health.empty else "All history", hr_latest).rename(columns={"Date": "Week"})
                hr_figure = go.Figure()
                hr_figure.add_scatter(x=weekly_hr["Week"], y=weekly_hr["median_hr"], mode="markers", name="Weekly median", marker={"color": "#86A7D4", "size": 8}, customdata=weekly_hr["runs"], hovertemplate="Week of %{x|%b %-d}<br>Median: %{y:.0f} bpm<br>%{customdata} run(s)<extra></extra>")
                hr_figure.add_scatter(x=weekly_hr["Week"], y=weekly_hr["rolling_hr"], mode="lines", name="4-week median", line={"color": "#D9A36A", "width": 3}, hovertemplate="Smoothed median: %{y:.0f} bpm<extra></extra>")
                hr_figure.update_layout(xaxis_title="Week beginning", yaxis_title="Average heart rate (bpm)", hovermode="x unified", legend_title_text="")
                st.plotly_chart(hr_figure, width="stretch", theme=None)
                st.caption("Outdoor runs only; treadmill runs are excluded. Dots show the weekly median across recorded run averages; the line smooths four run-weeks.")
            else:
                st.info("No run average heart-rate measurements are available.")

    with st.expander("Data coverage and original Garmin responses"):
        if not health.empty:
            coverage = health.groupby("Metric").agg(
                First=("Date", "min"), Last=("Date", "max"), Readings=("Value", "count"),
            ).rename(columns={"First": "First available", "Last": "Last available"}).reset_index()
            st.dataframe(coverage, hide_index=True, width="stretch")
        if snapshots:
            source = st.selectbox("Saved data source", sorted({snapshot["source"] for snapshot in snapshots}))
            options = [snapshot for snapshot in snapshots if snapshot["source"] == source]
            index = st.selectbox("Saved date window", range(len(options)), format_func=lambda value: f"{options[value]['start_date']} to {options[value]['end_date']}")
            st.json(options[index]["payload"])
        else:
            st.caption("No original wellness payloads are saved yet.")

    visible_activities = [activity for activity in activities if "treadmill" not in activity.activity_type.lower()]
    render_training_chat(visible_activities, snapshots, repository, current_page="health")


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


def _render_recovery_card(card, health, metric, wellness_end):
    if wellness_end is None:
        card.metric(f"{metric} · 7-day average", "Unavailable")
        return
    current, current_count, previous, previous_count = _calendar_window_means(health, metric, wellness_end)
    if current is None or previous is None or current_count < 4 or previous_count < 4:
        card.metric(f"{metric} · 7-day average", "Unavailable")
        card.caption(f"Need more recorded days (current {current_count}/7, previous {previous_count}/7).")
        return
    units = {"Sleep duration": ("h", 1), "Sleep score": ("pts", 0), "Resting heart rate": ("bpm", 0), "Nightly HRV": ("ms", 0), "Body Battery": ("pts", 0), "Steps": ("steps", 0)}
    unit, decimals = units[metric]
    value = f"{current:,.{decimals}f} {unit}"
    delta = current - previous
    change = f"{delta:+,.{decimals}f} {unit} vs prior 7d"
    card.metric(f"{metric} · 7-day avg", value, delta=change, delta_color="off", help=f"{current_count}/7 days recorded; comparison week has {previous_count}/7 days.")


def _calendar_window_means(health, metric, end_date):
    values = health[health["Metric"] == metric][["Date", "Value"]].copy()
    if values.empty:
        return None, 0, None, 0
    values["Date"] = pd.to_datetime(values["Date"]).dt.normalize()
    end = pd.Timestamp(end_date).normalize()
    current_start, previous_start = end - timedelta(days=6), end - timedelta(days=13)
    current = values[(values["Date"] >= current_start) & (values["Date"] <= end)]["Value"]
    previous = values[(values["Date"] >= previous_start) & (values["Date"] < current_start)]["Value"]
    return (
        float(current.mean()) if not current.empty else None, len(current),
        float(previous.mean()) if not previous.empty else None, len(previous),
    )


def _recovery_story(health, wellness_end):
    if wellness_end is None:
        return "Sync wellness history to establish a baseline before interpreting recovery trends."
    sleep, sleep_n, prior_sleep, prior_sleep_n = _calendar_window_means(health, "Sleep duration", wellness_end)
    score, score_n, prior_score, prior_score_n = _calendar_window_means(health, "Sleep score", wellness_end)
    resting, resting_n, prior_resting, prior_resting_n = _calendar_window_means(health, "Resting heart rate", wellness_end)
    hrv, hrv_n, prior_hrv, prior_hrv_n = _calendar_window_means(health, "Nightly HRV", wellness_end)
    if None in (sleep, prior_sleep, score, prior_score, resting, prior_resting):
        return "There are not enough complete recovery readings from two adjacent weeks to describe a change yet."
    sleep_delta = sleep - prior_sleep
    score_delta = score - prior_score
    resting_delta = resting - prior_resting
    date_start = pd.Timestamp(wellness_end).normalize() - timedelta(days=6)
    narrative = (
        f"For {date_start:%b %-d}–{pd.Timestamp(wellness_end):%b %-d}, sleep averaged {sleep:.1f} h "
        f"({sleep_delta:+.1f} h versus the previous week) and score averaged {score:.0f} "
        f"({score_delta:+.0f} points). Resting heart rate averaged {resting:.0f} bpm "
        f"({resting_delta:+.1f} bpm)."
    )
    if hrv is not None and prior_hrv is not None:
        narrative += f" Nightly HRV was {hrv:.0f} ms versus {prior_hrv:.0f} ms the week before."
    if sleep_delta < -0.4 and score_delta < -5 and abs(resting_delta) <= 2:
        narrative += " Sleep measures softened while resting heart rate stayed near its prior level. Treat this as a one-week signal; check how you feel and whether the pattern continues before changing training."
    else:
        narrative += " These are short-term comparisons, not a recovery verdict. Check whether the pattern continues and compare it with how you feel."
    return narrative


def _filter_date_window(frame, window, latest_date):
    if latest_date is None or window == "All history":
        return frame.copy()
    latest = pd.Timestamp(latest_date)
    start = latest - pd.Timedelta(weeks=12) if window == "Last 12 weeks" else latest - pd.DateOffset(months=6)
    return frame[frame["Date"] >= start].copy()


main()
