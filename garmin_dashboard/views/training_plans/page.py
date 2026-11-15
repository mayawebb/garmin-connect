"""Saved training plans generated through the shared OpenAI chat launcher."""

import streamlit as st

from garmin_dashboard.config import DATABASE_PATH
from garmin_dashboard.storage import ActivityRepository
from garmin_dashboard.views.chat_widget import render_training_chat


def main():
    st.title("Training Plans")
    st.caption("Ask for a running, strength, cross-training or recovery plan with the chat button at the lower right. Plans are saved locally.")
    st.info("Plans use your synced activity and wellness summaries through OpenAI. They are general training ideas, not medical advice or guaranteed race predictions.")
    repository = ActivityRepository(DATABASE_PATH)
    repository.initialize()
    activities = repository.list_activities()
    st.subheader("Saved plans")
    saved = repository.list_training_plans()
    if not saved:
        st.caption("Plans you create here will appear in this list and stay on this computer.")
    else:
        selected_id = st.session_state.get("selected_training_plan", saved[0]["plan_id"])
        ids = [item["plan_id"] for item in saved]
        if selected_id not in ids:
            selected_id = saved[0]["plan_id"]
        selected = st.selectbox(
            "Choose a saved plan",
            ids,
            index=ids.index(selected_id),
            format_func=lambda plan_id: _plan_label(next(item for item in saved if item["plan_id"] == plan_id)),
        )
        st.session_state["selected_training_plan"] = selected
        saved_plan = next(item for item in saved if item["plan_id"] == selected)
        _render_plan(saved_plan)
    render_training_chat(activities, repository.list_wellness_snapshots(), repository, current_page="training_plans")


def _plan_label(item):
    return f"{item['title']} · {item['created_at']:%Y-%m-%d}"


def _render_plan(item):
    plan = item["plan"]
    st.markdown(f"### {plan['title']}")
    st.caption(f"Goal: {plan['goal']} · {plan['duration_weeks']} weeks · Saved {item['created_at']:%Y-%m-%d %H:%M}")
    for week in plan["weeks"]:
        with st.expander(f"Week {week['week']} · {week['focus']}", expanded=week["week"] == 1):
            for session in week["sessions"]:
                st.markdown(f"**{session['day']} · {session['activity'].replace('_', ' ').title()}**  \n{session['details']}")
    st.markdown("**Recovery notes**")
    st.write(plan["recovery_notes"])
    st.caption(f"Original request: {item['prompt']}")


main()
