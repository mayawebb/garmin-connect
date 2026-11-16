"""Running and multisport analytics page."""

from datetime import datetime, timedelta
import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from garmin_dashboard.activity_streams import ActivityStreamPoint, parse_activity_zip
from garmin_dashboard.analytics import (
    estimate_lactate_threshold,
    format_duration_seconds,
    format_pace_min_km,
    median_running_pace,
    predicted_5k_trend,
    weekly_running_distance_calendar,
)
from garmin_dashboard.config import DATABASE_PATH, GARMIN_API_KEY
from garmin_dashboard.garmin_client import GarminApiError, GarminClient
from garmin_dashboard.models import Activity
from garmin_dashboard.sample_data import sample_activities
from garmin_dashboard.storage import ActivityRepository
from garmin_dashboard.views.common import activity_frame
from garmin_dashboard.views.chat_widget import render_training_chat


PALETTE = {"Running": "#70C3A2", "Strength Training": "#D9A36A", "Yoga": "#9A8BD2", "Cardio": "#86A7D4"}


def main():
    st.title("Analytics")
    st.caption("What changed in your training, and what the recorded numbers actually mean.")
    repository = ActivityRepository(DATABASE_PATH)
    repository.initialize()
    activities = repository.list_activities()
    using_sample = not activities
    if using_sample:
        activities = sample_activities()
        st.info("No Garmin activity records are stored yet. Showing synthetic sample data.")
    visible_activities = [a for a in activities if "treadmill" not in a.activity_type.lower()]
    frame = activity_frame(visible_activities)
    run_frame = frame[frame["Type"].str.contains("run", case=False, na=False) & ~frame["Type"].str.contains("treadmill", case=False, na=False)].copy()
    running_weeks = pd.DataFrame(weekly_running_distance_calendar(visible_activities))
    if not running_weeks.empty:
        running_weeks["week_start"] = pd.to_datetime(running_weeks["week_start"])
        running_weeks["rolling_4_week_km"] = running_weeks["distance_km"].rolling(4, min_periods=1).mean()
    latest_date = max((a.started_at.date() for a in visible_activities), default=None)
    latest_week = pd.Timestamp(latest_date - timedelta(days=latest_date.weekday())) if latest_date else None
    last_complete_week = latest_week if latest_date and latest_date.weekday() == 6 else latest_week - timedelta(days=7) if latest_week is not None else None
    complete_weeks = running_weeks[running_weeks["week_start"] <= last_complete_week].copy() if not running_weeks.empty and last_complete_week is not None else pd.DataFrame()
    if not running_weeks.empty and last_complete_week is not None:
        running_weeks.loc[running_weeks["week_start"] > last_complete_week, "rolling_4_week_km"] = float("nan")

    if not run_frame.empty:
        known_distance = run_frame["Distance (km)"].dropna()
        median_pace = median_running_pace(visible_activities)
        average_week = complete_weeks["distance_km"].mean() if not complete_weeks.empty and complete_weeks["distance_km"].notna().all() else None
        metric_columns = st.columns(5)
        metric_columns[0].metric("Run sessions", len(run_frame))
        metric_columns[1].metric("Recorded run distance", f"{known_distance.sum():.1f} km" if len(known_distance) else "Unavailable")
        metric_columns[2].metric("Longest recorded run", f"{known_distance.max():.1f} km" if len(known_distance) else "Unavailable")
        metric_columns[3].metric("Typical run pace", format_pace_min_km(median_pace), help="Median of each outdoor run's average pace. 6:38 /km means 6 minutes 38 seconds to cover one kilometer; hills and effort vary by run.")
        metric_columns[4].metric(
            "Avg distance / week",
            f"{average_week:.1f} km" if average_week is not None else "Unavailable",
            help="Mean across complete calendar weeks in the stored activity history. A week with no recorded run counts as 0 km; a run with missing distance remains unknown.",
        )
        if average_week is not None:
            valid_paces = run_frame["Pace (min/km)"].notna().sum()
            st.caption(f"Pace uses minutes:seconds per kilometer. The typical pace above is {format_pace_min_km(median_pace)} across {valid_paces} outdoor runs with pace data; it is not a race-pace target.")

    st.subheader("Your recent training story")
    story = _recent_running_story(complete_weeks)
    if story:
        st.info(story)
    else:
        st.info("There are not yet eight complete calendar weeks of running history to compare training blocks.")

    chart_window = st.selectbox("Trend window", ["Last 12 weeks", "Last 6 months", "All history"], index=1, key="analytics_window")
    if not running_weeks.empty and running_weeks["distance_km"].notna().any():
        visible_weeks = _filter_week_window(running_weeks, chart_window, latest_date)
        distance_figure = go.Figure()
        distance_figure.add_bar(
            x=visible_weeks["week_start"], y=visible_weeks["distance_km"], name="Weekly distance",
            marker_color=PALETTE["Running"],
            customdata=visible_weeks["run_count"],
            hovertemplate="Week of %{x|%b %-d}<br>%{y:.1f} km<br>%{customdata} run(s)<extra></extra>",
        )
        distance_figure.add_scatter(
            x=visible_weeks["week_start"], y=visible_weeks["rolling_4_week_km"],
            mode="lines", name="4-week average", line={"color": PALETTE["Strength Training"], "width": 3},
            hovertemplate="4-week average: %{y:.1f} km/week<extra></extra>",
        )
        distance_figure.update_layout(xaxis_title="Week beginning", yaxis_title="Running distance (km)", hovermode="x unified", legend_title_text="")
        distance_figure.update_yaxes(rangemode="tozero")
        st.subheader("Running distance")
        st.plotly_chart(distance_figure, width="stretch", theme=None)
        st.caption("Bars include calendar weeks with no recorded runs as 0 km. The amber line smooths each four-week block; an incomplete latest week is excluded from averages.")
    else:
        st.info("No running distances were returned for this history.")

    st.subheader("Pace trend")
    pace_data = run_frame.dropna(subset=["Pace (min/km)"]).copy()
    if not pace_data.empty:
        pace_data["Week"] = pace_data["Date"].dt.to_period("W-SUN").dt.start_time
        weekly_pace = pace_data.groupby("Week", as_index=False).agg(
            median_pace=("Pace (min/km)", "median"), runs=("Activity ID", "count"),
        ).sort_values("Week")
        weekly_pace["rolling_pace"] = weekly_pace["median_pace"].rolling(4, min_periods=2).median()
        visible_pace = _filter_week_window(weekly_pace.rename(columns={"Week": "week_start"}), chart_window, latest_date)
        visible_pace = visible_pace.rename(columns={"week_start": "Week"})
        visible_pace["median_label"] = visible_pace["median_pace"].map(format_pace_min_km)
        visible_pace["rolling_label"] = visible_pace["rolling_pace"].map(format_pace_min_km)
        pace_figure = go.Figure()
        pace_figure.add_scatter(
            x=visible_pace["Week"], y=visible_pace["median_pace"], mode="markers", name="Weekly median",
            marker={"size": 8, "color": PALETTE["Running"]}, customdata=visible_pace[["median_label", "runs"]],
            hovertemplate="Week of %{x|%b %-d}<br>Median pace: %{customdata[0]}<br>%{customdata[1]} run(s)<extra></extra>",
        )
        pace_figure.add_scatter(
            x=visible_pace["Week"], y=visible_pace["rolling_pace"], mode="lines", name="4-week median",
            line={"width": 3, "color": PALETTE["Strength Training"]}, customdata=visible_pace["rolling_label"],
            hovertemplate="Smoothed pace: %{customdata}<extra></extra>",
        )
        pace_figure.update_yaxes(autorange="reversed", title="Pace (min:sec per km; faster at top)", **_pace_axis_ticks(visible_pace["median_pace"]))
        pace_figure.update_layout(xaxis_title="Week beginning", hovermode="x unified", legend_title_text="")
        st.plotly_chart(pace_figure, width="stretch", theme=None)
        st.caption("Each dot is the median pace of runs that week; the line is a trailing four-run-week median. Hover for run counts. Weather, hills, distance, and workout effort affect pace.")
    else:
        st.info("Pace needs both a recorded distance and duration.")

    with st.expander("Run effort detail: pace and heart rate"):
        effort_data = run_frame.dropna(subset=["Pace (min/km)", "Avg heart rate (bpm)"]).copy()
        if not effort_data.empty:
            effort_data["Pace label"] = effort_data["Pace (min/km)"].map(format_pace_min_km)
            effort_figure = go.Figure()
            for activity_type, group in effort_data.groupby("Type"):
                customdata = [
                    [row["Date"].strftime("%b %-d, %Y"), row["Pace label"], row["Distance (km)"]]
                    for _, row in group.iterrows()
                ]
                effort_figure.add_scatter(
                    x=group["Avg heart rate (bpm)"], y=group["Pace (min/km)"], mode="markers", name=activity_type,
                    customdata=customdata, marker={"size": 8},
                    hovertemplate="%{customdata[0]}<br>%{x:.0f} bpm<br>%{customdata[1]}<br>Distance %{customdata[2]:.1f} km<extra>%{fullData.name}</extra>",
                )
            effort_figure.update_layout(xaxis_title="Average heart rate (bpm)", yaxis_title="Pace (min:sec/km)")
            effort_figure.update_yaxes(autorange="reversed", **_pace_axis_ticks(effort_data["Pace (min/km)"]))
            st.plotly_chart(effort_figure, width="stretch", theme=None)
            st.caption("This is context, not an efficiency score: faster pace at a given heart rate can suggest progress, but route, weather, workout type, and sensor accuracy matter.")
        else:
            st.info("Heart-rate versus pace analysis needs both measures on a run.")

    st.subheader("5K equivalent from recorded efforts")
    prediction_rows = predicted_5k_trend(visible_activities)
    if prediction_rows:
        prediction_frame = pd.DataFrame(prediction_rows)
        prediction_frame = prediction_frame.sort_values("date")
        prediction_frame["smoothed_seconds"] = prediction_frame["predicted_5k_seconds"].rolling(5, min_periods=2).median()
        prediction_frame["time_label"] = prediction_frame["predicted_5k_seconds"].map(format_duration_seconds)
        prediction_frame["smoothed_label"] = prediction_frame["smoothed_seconds"].map(format_duration_seconds)
        best_prediction = prediction_frame.loc[prediction_frame["predicted_5k_seconds"].idxmin()]
        st.metric("Fastest effort-based 5K estimate", format_duration_seconds(best_prediction["predicted_5k_seconds"]), help="Riegel estimate from one outdoor run's average pace. A training run may not represent an all-out 5K.")
        prediction_visible = prediction_frame[prediction_frame["date"] >= _window_start(chart_window, latest_date)] if chart_window != "All history" and latest_date else prediction_frame
        prediction_figure = go.Figure()
        prediction_figure.add_scatter(
            x=prediction_visible["date"], y=prediction_visible["predicted_5k_seconds"], mode="markers", name="Per-run estimate",
            marker={"size": 6, "color": "#8A9992", "opacity": 0.55},
            customdata=prediction_visible[["source_distance_km", "time_label"]],
            hovertemplate="%{x|%b %-d, %Y}<br>5K equivalent: %{customdata[1]}<br>Source run: %{customdata[0]:.1f} km<extra></extra>",
        )
        prediction_figure.add_scatter(
            x=prediction_visible["date"], y=prediction_visible["smoothed_seconds"], mode="lines", name="5-run median",
            line={"color": PALETTE["Running"], "width": 3}, customdata=prediction_visible["smoothed_label"],
            hovertemplate="Smoothed equivalent: %{customdata}<extra></extra>",
        )
        time_ticks = _duration_axis_ticks(prediction_visible["predicted_5k_seconds"])
        prediction_figure.update_yaxes(title="Equivalent 5K finish", autorange="reversed", tickmode="array", tickvals=time_ticks, ticktext=[format_duration_seconds(value) for value in time_ticks])
        prediction_figure.update_layout(xaxis_title="Run date", hovermode="x unified", legend_title_text="")
        st.plotly_chart(prediction_figure, width="stretch", theme=None)
        st.caption("Each point extrapolates one run's average pace to 5 km; the line smooths five runs. Treat it as a training-effort trend, not a race prediction. Treadmill runs are excluded.")
    else:
        st.info("No outdoor run of at least 2 km with recorded distance and duration is available for a 5K estimate.")

    st.subheader("Strength, cardio, and mobility")
    selected_start = _window_start(chart_window, latest_date)
    other_window = frame[frame["Date"] >= selected_start] if selected_start is not None else frame
    strength, cardio, yoga = st.columns(3)
    strength_frame = other_window[other_window["Type"].str.contains("strength", case=False, na=False)]
    yoga_frame = other_window[other_window["Type"].str.contains("yoga|pilates", case=False, na=False)]
    running_mask = other_window["Type"].str.contains("run", case=False, na=False)
    strength_mask = other_window["Type"].str.contains("strength", case=False, na=False)
    yoga_mask = other_window["Type"].str.contains("yoga|pilates", case=False, na=False)
    cardio_frame = other_window[~(running_mask | strength_mask | yoga_mask)]
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
        st.markdown("**Cardio and other sports**")
        if not cardio_frame.empty:
            cardio_frame = cardio_frame.dropna(subset=["Duration (min)"])
            if not cardio_frame.empty:
                cardio_frame = cardio_frame.assign(Week=cardio_frame["Date"].dt.to_period("W-SUN").dt.start_time)
                weekly_cardio = cardio_frame.groupby("Week", as_index=False)["Duration (min)"].sum()
                st.plotly_chart(px.bar(weekly_cardio, x="Week", y="Duration (min)", color_discrete_sequence=[PALETTE["Cardio"]]), width="stretch", theme=None)
            kinds = ", ".join(sorted(cardio_frame["Type"].dropna().unique()))
            st.caption(f"Recorded minutes per week. Included: {kinds}.")
        else:
            st.caption("No non-running, non-strength, or mobility activities in this window.")
    with yoga:
        st.markdown("**Yoga and mobility**")
        if not yoga_frame.empty:
            yoga_weekly = yoga_frame.assign(Week=yoga_frame["Date"].dt.to_period("W-SUN").dt.start_time).groupby("Week", as_index=False).size()
            st.plotly_chart(px.bar(yoga_weekly, x="Week", y="size", color_discrete_sequence=[PALETTE["Yoga"]], labels={"size": "Sessions"}), width="stretch", theme=None)
            yoga_minutes = yoga_frame["Duration (min)"].dropna().sum()
            st.caption(f"{len(yoga_frame)} sessions; {yoga_minutes:.0f} recorded minutes where available.")
        else:
            st.caption("No yoga or Pilates sessions found.")

    st.subheader("Other workouts: recent four-week comparison")
    mix_rows, mix_story = _activity_mix_comparison(frame, complete_weeks)
    if mix_rows:
        st.dataframe(pd.DataFrame(mix_rows), hide_index=True, width="stretch")
        st.caption(mix_story + " Session counts are exact records; duration and set totals include only values Garmin returned.")
    else:
        st.info("There are not yet eight complete weeks to compare strength, cardio, and mobility activity.")

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
                lt_left.metric("Estimated threshold pace", format_pace_min_km(estimate.pace_min_km))
                lt_right.metric("Estimated threshold heart rate", f"{estimate.heart_rate_bpm:.0f} bpm")
                st.caption(estimate.method + ". Use this only as a training estimate; confirm with a qualified test if precision matters.")
            elif confirmed:
                st.info("This FIT file lacks the continuous speed and heart-rate samples needed for the estimate.")

    st.subheader("Activity history")
    history_display = frame.copy()
    history_display["Pace"] = history_display["Pace (min/km)"].map(format_pace_min_km)
    history_display.loc[~history_display["Type"].str.contains("run", case=False, na=False), "Pace"] = "—"
    history_display = history_display.drop(columns=["Pace (min/km)"])
    st.dataframe(history_display.sort_values("Date", ascending=False), hide_index=True, width="stretch")
    render_training_chat(visible_activities, repository.list_wellness_snapshots(), repository, current_page="analytics")


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


def _activity_mix_comparison(frame, complete_weeks):
    if len(complete_weeks) < 8:
        return [], ""
    blocks = complete_weeks.sort_values("week_start").tail(8)
    previous_start = blocks.iloc[0]["week_start"]
    recent_start = blocks.iloc[4]["week_start"]
    end = blocks.iloc[-1]["week_start"] + timedelta(days=7)
    previous_rows = frame[(frame["Date"] >= previous_start) & (frame["Date"] < recent_start)]
    recent_rows = frame[(frame["Date"] >= recent_start) & (frame["Date"] < end)]
    category_masks = {
        "Strength": lambda data: data["Type"].str.contains("strength", case=False, na=False),
        "Cardio and other sports": lambda data: ~(
            data["Type"].str.contains("run|strength|yoga|pilates", case=False, na=False)
        ),
        "Yoga and Pilates": lambda data: data["Type"].str.contains("yoga|pilates", case=False, na=False),
    }
    rows, summaries = [], []
    for label, mask in category_masks.items():
        before, after = previous_rows[mask(previous_rows)], recent_rows[mask(recent_rows)]
        durations = after["Duration (min)"].dropna()
        sets = after["Total sets"].dropna()
        rows.append({
            "Activity type": label,
            "Previous 4 weeks · sessions": len(before),
            "Latest 4 weeks · sessions": len(after),
            "Latest recorded minutes": round(durations.sum(), 0) if not durations.empty else None,
            "Latest recorded sets": round(sets.sum(), 0) if not sets.empty else None,
        })
        summaries.append(f"{label.lower()}: {len(before)} to {len(after)} sessions")
    return rows, "Across the last four complete weeks versus the four before: " + "; ".join(summaries) + "."


def _window_start(window, latest_date):
    if latest_date is None or window == "All history":
        return None
    latest = pd.Timestamp(latest_date)
    if window == "Last 12 weeks":
        return latest - pd.Timedelta(weeks=12)
    return latest - pd.DateOffset(months=6)


def _filter_week_window(frame, window, latest_date):
    start = _window_start(window, latest_date)
    if start is None:
        return frame.copy()
    date_column = "week_start" if "week_start" in frame.columns else "Week"
    return frame[frame[date_column] >= start].copy()


def _pace_axis_ticks(values):
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {}
    lower = math.floor(clean.min() * 4)
    upper = math.ceil(clean.max() * 4)
    if lower == upper:
        lower -= 1
        upper += 1
    tick_values = [quarter / 4 for quarter in range(lower, upper + 1, 2)]
    return {
        "tickmode": "array",
        "tickvals": tick_values,
        "ticktext": [format_pace_min_km(value).replace(" /km", "") for value in tick_values],
    }


def _duration_axis_ticks(values):
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return []
    step = 60
    lower = math.floor(clean.min() / step) * step
    upper = math.ceil(clean.max() / step) * step
    if lower == upper:
        lower -= step
        upper += step
    return list(range(lower, upper + 1, step))


def _recent_running_story(complete_weeks):
    if len(complete_weeks) < 8:
        return None
    blocks = complete_weeks.sort_values("week_start").tail(8)
    previous, recent = blocks.iloc[:4], blocks.iloc[4:]
    if previous["distance_km"].isna().any() or recent["distance_km"].isna().any():
        return "Some runs in the latest eight weeks have no recorded distance, so a complete volume comparison is not available."
    previous_km = float(previous["distance_km"].sum())
    recent_km = float(recent["distance_km"].sum())
    previous_runs = int(previous["run_count"].sum())
    recent_runs = int(recent["run_count"].sum())
    previous_avg = previous_km / 4
    recent_avg = recent_km / 4
    change = (recent_km / previous_km - 1) * 100 if previous_km > 0 else None
    if change is None:
        return f"The latest four complete weeks averaged {recent_avg:.1f} km per week across {recent_runs} runs. There is no prior running volume to compare yet."
    previous_run_length = previous_km / previous_runs if previous_runs else None
    recent_run_length = recent_km / recent_runs if recent_runs else None
    story = (
        f"The latest four complete weeks averaged {recent_avg:.1f} km per week ({recent_km:.1f} km total), "
        f"up {change:.0f}% from {previous_avg:.1f} km/week in the previous four. "
        f"You recorded {recent_runs} runs versus {previous_runs} before."
    )
    if previous_run_length is not None and recent_run_length is not None:
        story += f" Average run length changed from {previous_run_length:.1f} to {recent_run_length:.1f} km."
    if change >= 15:
        story += " Most of the increase came from longer outings, so hold near this level for another block before adding more distance."
    elif recent_runs < previous_runs and recent_km >= previous_km:
        story += " Volume held or rose with fewer runs; a short easy run could spread the load if you want more weekly frequency."
    else:
        story += " Keep this schedule steady and watch whether the next block confirms the direction."
    return story


main()
