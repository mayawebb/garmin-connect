"""Shared OpenAI chat launcher used by every dashboard section."""

import re

import pandas as pd
import plotly.express as px
import streamlit as st

from ..analytics import format_pace_min_km
from ..chat_context import ACTIVITY_METRICS, HEALTH_PREFIX, training_context
from ..chat import ChatError, ChartRequest, ask_openai, build_chart_data, generate_training_plan
from ..config import OPENAI_API_KEY, OPENAI_MODEL
from ..views.common import activity_frame
from ..wellness import wellness_metric_points


def render_training_chat(activities, snapshots, repository, *, current_page: str) -> None:
    """Render one floating, page-independent chat launcher and its chart output."""
    st.markdown("""
    <style>
    .st-key-global_training_chat { position: fixed; right: 1.4rem; bottom: 1.1rem; z-index: 10000; }
    .st-key-global_training_chat > div > button { border-radius: 999px; width: 3.6rem; height: 3.6rem; box-shadow: 0 4px 16px #172c2a33; font-size: 1.25rem; }
    div[data-testid="stPopoverBody"] { max-height: 76vh; overflow-y: auto; }
    </style>
    """, unsafe_allow_html=True)

    points = wellness_metric_points(snapshots)
    activity_metrics = dict(ACTIVITY_METRICS)
    health_metrics = sorted({point.metric for point in points})
    allowed_metrics = set(activity_metrics) | {HEALTH_PREFIX + metric for metric in health_metrics}
    context = training_context(activities, points)
    history = st.session_state.setdefault("global_chat_history", [])

    with st.popover("💬", key="global_training_chat", help="Ask about your Garmin training and health data", type="primary", width="content"):
        st.markdown("### Training assistant")
        st.caption("OpenAI uses a compact summary of synced Garmin data. Requests are not sent if the API key is missing.")
        if not OPENAI_API_KEY:
            st.info("Add OPENAI_API_KEY to your local .env file, then restart Streamlit to enable chat.")
        for message in history[-8:]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        with st.form("global_chat_form", clear_on_submit=True):
            question = st.text_input("Ask a question or request a chart", placeholder="Based on my data, what is my predicted 5K time?")
            submitted = st.form_submit_button("Send", type="primary", disabled=not OPENAI_API_KEY)
        if submitted and question.strip():
            history.append({"role": "user", "content": question.strip()})
            st.session_state["global_chat_chart"] = None
            try:
                if _is_plan_request(question):
                    plan = generate_training_plan(
                        question.strip(), context, history=history[:-1], model=OPENAI_MODEL,
                    )
                    plan_id = repository.save_training_plan(question.strip(), plan.as_dict())
                    st.session_state["selected_training_plan"] = plan_id
                    answer = f"Saved **{plan.title}** as a {plan.duration_weeks}-week training plan. Open Training Plans to review it."
                else:
                    result = ask_openai(
                        question.strip(), allowed_metrics, context,
                        history=history[:-1], model=OPENAI_MODEL,
                    )
                    answer = result.answer
                    if result.metric:
                        st.session_state["global_chat_chart"] = result
                history.append({"role": "assistant", "content": answer})
            except ChatError as exc:
                history.append({"role": "assistant", "content": str(exc)})
            st.rerun()

        chart_request = st.session_state.get("global_chat_chart")
        if chart_request and chart_request.metric:
            _render_requested_chart(chart_request, activities, points)
        st.caption(f"Current context: {current_page.replace('_', ' ')} · charts use only available recorded metrics.")


def _is_plan_request(question: str) -> bool:
    return bool(re.search(r"\b(plan|training block|weekly schedule|build me a schedule)\b", question, re.I))


def _render_requested_chart(request: ChartRequest, activities, points) -> None:
    if request.metric.startswith(HEALTH_PREFIX):
        frame = _wellness_chart_frame(request, points)
        value_column = "Value"
        x_column = "Period" if request.group_by in {"week", "month"} else "Date"
    else:
        frame = build_chart_data(activity_frame(activities), request)
        value_column = ACTIVITY_METRICS.get(request.metric, "")
        x_column = {"week": "Period", "month": "Period", "activity_type": "Type", "none": "Date"}[request.group_by]
    if frame.empty:
        st.info("There are no recorded values for that chart request.")
        return
    if request.metric == "pace_min_km":
        frame["Pace (min:sec/km)"] = frame[value_column].map(format_pace_min_km)
        hover_data = {"Pace (min:sec/km)": True, value_column: False}
        chart = px.line(frame, x=x_column, y=value_column, markers=True, hover_data=hover_data) if request.chart_type == "line" else px.bar(frame, x=x_column, y=value_column, hover_data=hover_data)
        clean = pd.to_numeric(frame[value_column], errors="coerce").dropna()
        if not clean.empty:
            lower, upper = int(clean.min() * 4), int(clean.max() * 4 + 0.999)
            ticks = [value / 4 for value in range(lower, upper + 1, 2)]
            chart.update_yaxes(tickmode="array", tickvals=ticks, ticktext=[format_pace_min_km(value).replace(" /km", "") for value in ticks], autorange="reversed", title="Pace (min:sec/km; faster up)")
    else:
        chart = px.line(frame, x=x_column, y=value_column, markers=True) if request.chart_type == "line" else px.bar(frame, x=x_column, y=value_column)
    st.plotly_chart(chart, width="stretch", theme=None)


def _wellness_chart_frame(request: ChartRequest, points):
    metric_id = request.metric.removeprefix(HEALTH_PREFIX)
    rows = [{"Date": pd.Timestamp(point.day), "Value": point.value} for point in points if point.metric == metric_id]
    frame = pd.DataFrame(rows)
    if frame.empty or request.group_by == "activity_type":
        return pd.DataFrame()
    if request.group_by in {"week", "month"}:
        rule = "W-SUN" if request.group_by == "week" else "M"
        frame["Period"] = frame["Date"].dt.to_period(rule).dt.start_time
        frame = frame.groupby("Period", as_index=False)["Value"].mean()
    return frame.sort_values("Date" if "Date" in frame else "Period")
