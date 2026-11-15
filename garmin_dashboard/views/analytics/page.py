"""Running and multisport analytics page."""

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from garmin_dashboard.activity_streams import ActivityStreamPoint, parse_activity_zip
from garmin_dashboard.analytics import (
    average_weekly_running_distance,
    estimate_lactate_threshold,
    median_running_pace,
    predicted_5k_trend,
    weekly_running_distance,
)
from garmin_dashboard.config import DATABASE_PATH, GARMIN_API_KEY
from garmin_dashboard.garmin_client import GarminApiError, GarminClient
from garmin_dashboard.models import Activity
from garmin_dashboard.sample_data import sample_activities
from garmin_dashboard.storage import ActivityRepository
from garmin_dashboard.views.common import activity_frame
from garmin_dashboard.views.chat_widget import render_training_chat


PALETTE = {"Running": "#43866c", "Strength Training": "#d97a4e", "Yoga": "#7778a8", "Cardio": "#4382a0"}


def main():
    st.title("Analytics")
    st.caption("Training progression across runs, strength, cardio and mobility. Distances in km; running pace in min/km.")
    repository = ActivityRepository(DATABASE_PATH)
    repository.initialize()
    activities = repository.list_activities()
    using_sample = not activities
    if using_sample:
        activities = sample_activities()
        st.info("No Garmin activity records are stored yet. Showing synthetic sample data.")
    frame = activity_frame(activities)
    run_frame = frame[frame["Type"].str.contains("run", case=False, na=False) & ~frame["Type"].str.contains("treadmill", case=False, na=False)].copy()
    running_weeks = pd.DataFrame(weekly_running_distance(activities))

    if not run_frame.empty:
        known_distance = run_frame["Distance (km)"].dropna()
        median_pace = median_running_pace(activities)
        average_week = average_weekly_running_distance(activities)
        metric_columns = st.columns(5)
        metric_columns[0].metric("Run sessions", len(run_frame))
        metric_columns[1].metric("Total running distance", f"{known_distance.sum():.1f} km" if len(known_distance) else "Unavailable")
        metric_columns[2].metric("Longest recorded run", f"{known_distance.max():.1f} km" if len(known_distance) else "Unavailable")
        metric_columns[3].metric("Median recorded pace", f"{median_pace:.2f} min/km" if median_pace is not None else "Unavailable")
        metric_columns[4].metric(
            "Average weekly distance",
            f"{average_week:.1f} km" if average_week is not None else "Unavailable",
            help="Mean of weeks with recorded outdoor running distance. Weeks with no run record are not treated as zero.",
        )

    st.subheader("Weekly running distance")
    if not running_weeks.empty and running_weeks["distance_km"].notna().any():
        st.plotly_chart(
            px.bar(running_weeks.dropna(subset=["distance_km"]), x="week_start", y="distance_km",
                   color_discrete_sequence=[PALETTE["Running"]], labels={"week_start": "Week beginning", "distance_km": "Distance (km)"}),
            width="stretch", theme=None,
        )
    else:
        st.info("No running distances were returned for this history.")

    st.subheader("Pace and effort")
    pace_left, pace_right = st.columns(2)
    with pace_left:
        pace_data = run_frame.dropna(subset=["Pace (min/km)"])
        if not pace_data.empty:
            pace_chart = px.scatter(pace_data, x="Date", y="Pace (min/km)", color="Type", hover_data=["Distance (km)", "Avg heart rate (bpm)"])
            pace_chart.update_yaxes(autorange="reversed", title="Pace (min/km), faster at top")
            st.plotly_chart(pace_chart, width="stretch", theme=None)
        else:
            st.info("Pace needs both a recorded distance and duration.")
    with pace_right:
        effort_data = run_frame.dropna(subset=["Pace (min/km)", "Avg heart rate (bpm)"])
        if not effort_data.empty:
            st.plotly_chart(px.scatter(
                effort_data, x="Avg heart rate (bpm)", y="Pace (min/km)", color="Type",
                hover_data=["Date", "Distance (km)"], labels={"Pace (min/km)": "Pace (min/km), lower is faster"},
            ).update_yaxes(autorange="reversed"), width="stretch", theme=None)
        else:
            st.info("Heart-rate versus pace analysis needs both measures on a run.")

    st.subheader("Predicted 5K time")
    prediction_rows = predicted_5k_trend(activities)
    if prediction_rows:
        prediction_frame = pd.DataFrame(prediction_rows)
        prediction_frame["Predicted 5K time (min)"] = prediction_frame["predicted_5k_seconds"] / 60
        best_prediction = prediction_frame.loc[prediction_frame["predicted_5k_seconds"].idxmin()]
        minutes = int(best_prediction["predicted_5k_seconds"] // 60)
        seconds = int(round(best_prediction["predicted_5k_seconds"] % 60))
        if seconds == 60:
            minutes, seconds = minutes + 1, 0
        st.metric("Best recorded-effort estimate", f"{minutes}:{seconds:02d}", help="Riegel estimate from outdoor activity average pace. It is not a guaranteed race result.")
        prediction_chart = px.line(
            prediction_frame, x="date", y="Predicted 5K time (min)", markers=True,
            hover_data={"activity_id": True, "source_distance_km": ":.1f", "Predicted 5K time (min)": ":.2f"},
            labels={"date": "Run date", "source_distance_km": "Source run (km)"},
        )
        prediction_chart.update_yaxes(title="Estimated 5K finish (minutes)", autorange="reversed")
        st.plotly_chart(prediction_chart, width="stretch", theme=None)
        st.caption("Each point uses that outdoor run’s average pace and the Riegel distance formula. Training efforts may not represent an all-out race; treadmill runs are excluded.")
    else:
        st.info("No outdoor run of at least 2 km with recorded distance and duration is available for a 5K estimate.")

    st.subheader("Other training")
    strength, cardio, yoga = st.columns(3)
    strength_frame = frame[frame["Type"].str.contains("strength", case=False, na=False)]
    cardio_frame = frame[frame["Type"].str.contains("cycling|cardio|swim|rowing|elliptical|hiking", case=False, na=False)]
    yoga_frame = frame[frame["Type"].str.contains("yoga|pilates", case=False, na=False)]
    with strength:
        st.markdown("**Strength**")
        sets = strength_frame.dropna(subset=["Total sets"])
        if not sets.empty:
            sets = sets.assign(Week=sets["Date"].dt.to_period("W-SUN").dt.start_time)
            weekly_sets = sets.groupby("Week", as_index=False)["Total sets"].sum()
            st.plotly_chart(px.bar(weekly_sets, x="Week", y="Total sets", color_discrete_sequence=[PALETTE["Strength Training"]]), width="stretch", theme=None)
            st.caption(f"Set totals are available for {len(sets)} strength activities. Per-exercise loads are not present in these summaries.")
        elif not strength_frame.empty:
            st.caption(f"{len(strength_frame)} strength sessions recorded; set totals were not returned.")
        else:
            st.caption("No strength sessions in the synced activity history.")
    with cardio:
        st.markdown("**Cardio**")
        if not cardio_frame.empty:
            cardio_frame = cardio_frame.dropna(subset=["Duration (min)"])
            if not cardio_frame.empty:
                cardio_frame = cardio_frame.assign(Week=cardio_frame["Date"].dt.to_period("W-SUN").dt.start_time)
                weekly_cardio = cardio_frame.groupby("Week", as_index=False)["Duration (min)"].sum()
                st.plotly_chart(px.bar(weekly_cardio, x="Week", y="Duration (min)", color_discrete_sequence=[PALETTE["Cardio"]]), width="stretch", theme=None)
            st.caption("Recorded non-running cardio minutes per week.")
        else:
            st.caption("No cycling, swimming, cardio-machine or hiking sessions found.")
    with yoga:
        st.markdown("**Yoga and mobility**")
        if not yoga_frame.empty:
            yoga_weekly = yoga_frame.assign(Week=yoga_frame["Date"].dt.to_period("W-SUN").dt.start_time).groupby("Week", as_index=False).size()
            st.plotly_chart(px.bar(yoga_weekly, x="Week", y="size", color_discrete_sequence=["#7778a8"], labels={"size": "Sessions"}), width="stretch", theme=None)
            yoga_minutes = yoga_frame["Duration (min)"].dropna().sum()
            st.caption(f"{len(yoga_frame)} sessions; {yoga_minutes:.0f} recorded minutes where available.")
        else:
            st.caption("No yoga or Pilates sessions found.")

    st.subheader("Training observations")
    observations = _training_observations(frame, running_weeks, strength_frame, cardio_frame, yoga_frame)
    for observation in observations:
        st.markdown(f"- {observation}")

    st.subheader("Lactate-threshold field estimate")
    st.caption("This is an estimate from a user-confirmed hard, evenly paced 30-minute test, not a blood lactate measurement. Garmin has not supplied a threshold value in the synced records.")
    eligible_runs = run_frame[run_frame["Duration (min)"].fillna(0) >= 30]
    if eligible_runs.empty:
        st.info("No 30-minute run is available to use as a field test.")
    else:
        run_id = st.selectbox(
            "Choose a 30-minute run to review",
            eligible_runs["Activity ID"].tolist(),
            format_func=lambda value: _run_label(value, eligible_runs),
            key="lt_activity",
        )
        stream = repository.get_activity_stream(str(run_id))
        if stream is None:
            if st.button("Import sensor data for this run", key="lt_import"):
                if not GARMIN_API_KEY:
                    st.warning("Set GARMIN_API_KEY in your local .env file first.")
                else:
                    with st.spinner("Downloading and parsing the selected FIT file…"):
                        try:
                            with GarminClient(GARMIN_API_KEY) as client:
                                archive = client.download_activity(str(run_id))
                            points = parse_activity_zip(archive)
                            repository.save_activity_stream(str(run_id), archive, [point.as_dict() for point in points])
                            st.rerun()
                        except (GarminApiError, ValueError) as exc:
                            st.error(str(exc))
            st.info("Import the run's FIT sensor records before estimating threshold pace and heart rate.")
        else:
            confirmed = st.checkbox("This was a hard, evenly paced 30-minute field test", key="lt_confirm")
            estimate = estimate_lactate_threshold(
                float(eligible_runs.loc[eligible_runs["Activity ID"] == run_id, "Duration (min)"].iloc[0]) * 60,
                [_stream_point(point) for point in stream],
                confirmed_threshold_test=confirmed,
            )
            if estimate:
                lt_left, lt_right = st.columns(2)
                lt_left.metric("Estimated threshold pace", f"{estimate.pace_min_km:.2f} min/km")
                lt_right.metric("Estimated threshold heart rate", f"{estimate.heart_rate_bpm:.0f} bpm")
                st.caption(estimate.method + ". Use this only as a training estimate; confirm with a qualified test if precision matters.")
            elif confirmed:
                st.info("This FIT file lacks the continuous speed and heart-rate samples needed for the estimate.")

    st.subheader("Activity history")
    st.dataframe(frame.sort_values("Date", ascending=False), hide_index=True, width="stretch")
    render_training_chat(activities, repository.list_wellness_snapshots(), repository, current_page="analytics")


def _run_label(activity_id, frame):
    selected = frame[frame["Activity ID"] == activity_id].iloc[0]
    return f"{selected['Date']:%Y-%m-%d} · {selected['Type']} · {selected['Distance (km)'] or 0:.1f} km"


def _stream_point(point: dict) -> ActivityStreamPoint:
    timestamp = datetime.fromisoformat(point["timestamp"]) if point.get("timestamp") else None
    return ActivityStreamPoint(
        timestamp=timestamp,
        heart_rate_bpm=point.get("heart_rate_bpm"),
        distance_m=point.get("distance_m"),
        speed_mps=point.get("speed_mps"),
        cadence_spm=point.get("cadence_spm"),
        altitude_m=point.get("altitude_m"),
    )


def _training_observations(frame, weekly_runs, strength_frame, cardio_frame, yoga_frame):
    items = []
    if not weekly_runs.empty:
        weeks = weekly_runs.sort_values("week_start").tail(8)
        recent = weeks.tail(4)
        previous = weeks.iloc[-8:-4]
        recent_km = recent["distance_km"].sum(min_count=1)
        recent_runs = int(recent["run_count"].sum())
        if pd.notna(recent_km):
            items.append(f"You logged {recent_km:.1f} km across {recent_runs} runs in the latest four recorded weeks. To build distance, keep this baseline consistent before adding another easy run or extending the long run.")
        if len(previous) == 4 and pd.notna(recent_km):
            previous_km = previous["distance_km"].sum(min_count=1)
            if pd.notna(previous_km) and previous_km > 0 and recent_km > previous_km * 1.2:
                items.append("Recorded running volume is up more than 20% from the prior four-week block; consider holding steady for a week before increasing again.")
        if len(weekly_runs) >= 3:
            items.append("For faster 5K–half-marathon times, a useful structure is mostly easy running plus one controlled tempo or interval session each week; the activity summaries do not identify all workout intensity reliably.")
    else:
        items.append("No running activities are recorded yet, so distance and pace progression are not available.")
    if not strength_frame.empty:
        sets = strength_frame["Total sets"].dropna()
        if len(sets):
            items.append(f"Strength-set totals are available for {len(sets)} sessions. The summaries do not include reliable per-exercise loads, so track exercise, weight and reps to see progressive overload.")
        else:
            items.append(f"You logged {len(strength_frame)} strength sessions. Set and load details were absent from the summaries; importing activity detail or recording exercises will make progress measurable.")
    if not cardio_frame.empty:
        minutes = cardio_frame["Duration (min)"].dropna().sum()
        items.append(f"You logged {len(cardio_frame)} cross-training cardio sessions ({minutes:.0f} minutes where duration was available); compare this weekly total as your running load changes.")
    if not yoga_frame.empty:
        items.append(f"You logged {len(yoga_frame)} yoga or Pilates sessions. Their recorded frequency and duration are shown above; no flexibility score is supplied by Garmin here.")
    return items


main()
