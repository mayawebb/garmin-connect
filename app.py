"""Streamlit router and shared Garmin synchronization controls."""

from datetime import date, timedelta

import streamlit as st
import plotly.io as pio
import plotly.graph_objects as go

from garmin_dashboard.config import DATABASE_PATH, GARMIN_API_KEY
from garmin_dashboard.garmin_client import GarminApiError, GarminClient
from garmin_dashboard.importer import sync_activities
from garmin_dashboard.storage import ActivityRepository
from garmin_dashboard.wellness import sync_wellness


st.set_page_config(page_title="Garmin Training Lab", page_icon="⛰️", layout="wide")
pio.templates["garmin_night"] = go.layout.Template(layout={
    "paper_bgcolor": "#111916",
    "plot_bgcolor": "#111916",
    "font": {"color": "#EAF1ED", "family": "Arial, sans-serif"},
    "colorway": ["#70C3A2", "#D9A36A", "#86A7D4", "#CF89A3", "#B6C879", "#9A8BD2"],
    "xaxis": {"gridcolor": "#2D3A35", "linecolor": "#46544E", "zerolinecolor": "#46544E"},
    "yaxis": {"gridcolor": "#2D3A35", "linecolor": "#46544E", "zerolinecolor": "#46544E"},
    "legend": {"bgcolor": "rgba(17,25,22,0.72)"},
})
pio.templates.default = "garmin_night"
st.markdown("""
<style>
:root { --ink: #eaf1ed; --paper: #111916; --panel: #1d2824; --surface: #25312c; --track: #70c3a2; --signal: #d9a36a; --slate: #a5b3ac; --line: #35433d; }
[data-testid="stAppViewContainer"], [data-testid="stMain"] { background: var(--paper); color: var(--ink); }
[data-testid="stSidebar"] { background: var(--panel); }
[data-testid="stSidebar"] * { color: var(--ink); }
[data-testid="stHeader"] { background: transparent; }
h1, h2, h3, p, label, [data-testid="stCaptionContainer"], [data-testid="stMarkdownContainer"] { color: var(--ink); }
h1, h2, h3 { letter-spacing: -0.025em; }
[data-testid="stMetricValue"] { color: var(--ink); font-variant-numeric: tabular-nums; }
[data-testid="stMetricLabel"] { color: var(--slate); }
.stButton > button[kind="primary"] { background: var(--track); border-color: var(--track); color: #10201a; }
.stButton > button { border-color: var(--line); background: var(--surface); color: var(--ink); }
.stButton > button:focus-visible, a:focus-visible, input:focus-visible { outline: 2px solid var(--track); outline-offset: 2px; }
[data-baseweb="input"] input, [data-baseweb="select"] *, [data-baseweb="textarea"] textarea { color: var(--ink); background-color: var(--surface); }
[data-testid="stPopover"] button { color: var(--ink); }
[data-testid="stDataFrame"] { border-color: var(--line); }
</style>
""", unsafe_allow_html=True)

repository = ActivityRepository(DATABASE_PATH)
repository.initialize()
activities = repository.list_activities()
with st.sidebar:
    st.title("Training Lab")
    st.caption(f"{len(activities)} activities stored locally")
    st.divider()
    if st.button("Sync all activities"):
        if not GARMIN_API_KEY:
            st.warning("Set GARMIN_API_KEY in your local .env file first.")
        else:
            with st.spinner("Syncing activity history…"):
                try:
                    with GarminClient(GARMIN_API_KEY) as client:
                        report = sync_activities(client, repository)
                    st.success(f"Imported {report.imported}; unchanged {report.skipped}; failed {report.failed}.")
                    st.rerun()
                except GarminApiError as exc:
                    st.error(str(exc))
    today = date.today()
    default_start = min((activity.started_at.date() for activity in activities), default=today - timedelta(days=90)) - timedelta(days=1)
    wellness_range = st.date_input(
        "Wellness history",
        value=(default_start, today),
        max_value=today,
    )
    if st.button("Sync wellness history"):
        if not GARMIN_API_KEY:
            st.warning("Set GARMIN_API_KEY in your local .env file first.")
        elif isinstance(wellness_range, (tuple, list)) and len(wellness_range) == 2:
            with st.spinner("Syncing daily summaries, sleep, and HRV…"):
                try:
                    with GarminClient(GARMIN_API_KEY) as client:
                        report = sync_wellness(client, repository, wellness_range[0], wellness_range[1])
                    st.success(f"Saved {report.imported}; unchanged {report.skipped}; failed windows {report.failed}.")
                    if report.errors:
                        st.warning("Some date windows failed: " + "; ".join(report.errors[:3]))
                    st.rerun()
                except GarminApiError as exc:
                    st.error(str(exc))

pages = {
    "ANALYTICS": [st.Page("garmin_dashboard/views/analytics/page.py", title="Analytics", icon="📈", url_path="analytics", default=True)],
    "HEALTH": [st.Page("garmin_dashboard/views/health/page.py", title="Health", icon="🫀", url_path="health")],
    "TRAINING PLANS": [st.Page("garmin_dashboard/views/training_plans/page.py", title="Training Plans", icon="🗓️", url_path="training-plans")],
}
page = st.navigation(pages, position="sidebar")
page.run()
