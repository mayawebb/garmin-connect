# Garmin Dashboard Redesign

## Intent

Turn the local Streamlit app into three clear workspaces: Analytics, Health, and Training Plans. Use the user's Garmin activity and wellness data, retain raw source records, and visibly distinguish measured values from estimates and unavailable metrics.

## User outcomes

- Explore weekly running distance, pace and running dynamics; estimate lactate threshold only from a user-designated 30-minute threshold field test with sufficient FIT samples.
- Review activity progression across running, strength, cardio, yoga and other recorded types. Suggestions must refer to observed frequency, volume or trends and avoid medical claims.
- Review heart rate, resting heart rate, sleep, HRV, stress, Body Battery and steps when Garmin returns them. Do not fabricate VO2 max or recovery metrics when the API omits them.
- Ask questions through a shared floating OpenAI chat launcher available on all pages. Generated training plans are validated and saved in SQLite.
- Show Riegel-based predicted 5K time estimates from outdoor runs; exclude treadmill activities from running progression charts.
- Backfill wellness history within documented endpoint behavior; chunk date ranges when an endpoint rejects a large window.

## Architecture and design decisions

- Use Streamlit's `st.navigation` with three named page groups and Python page modules under `garmin_dashboard/views/analytics/`, `health/`, and `training_plans/`.
- Keep Garmin access, normalization, analytics, chat validation, and persistence in their current service modules; pages compose these services.
- The Analytics page leads with a weekly outdoor running-distance chart, pace and prediction trends, and sport-specific analysis. A shared chat launcher floats at the lower right.
- The Health page presents observed signals with units, date coverage, and explicit empty states.
- The Training Plans page provides goal-focused chat, displays and persists generated plans, and lists saved plans.
- Use the user-requested OpenAI Responses API for chat; keep the API key in `.env`, disable response storage, send only compact training summaries and conversation text, and validate model output. Never execute model-generated code or SQL.
- Use Garmin-originated VO2 max/recovery fields only if present. An LT estimate requires an explicitly selected 30-minute hard, evenly paced test; otherwise show how to collect a valid effort.

## Research notes

- Intervals.icu emphasizes a long-term fitness/fatigue/form view, multisport trends, interval/activity analysis, and customizable charts.
- RUNALYZE emphasizes TRIMP, pace/distance trends, effective VO2 max, and marathon-shape context.
- Garmin Connect groups activity trends with health signals such as sleep score, Body Battery, and training status.
- This dashboard adopts a compact progression-first layout, separates health signals from training performance, and keeps sport-specific views available without claiming proprietary scores.

## Constraints and non-goals

- Keep the app local and SQLite-backed; keep `.env` and databases out of Git.
- Use kilometers, min/km, meters, seconds/minutes, and bpm with clear labels.
- Missing metrics stay missing. Health/training advice is informational and data-grounded, not diagnosis or guaranteed race outcomes.
- OpenAI API usage is metered and separate from ChatGPT billing. Do not add other paid services, invent Garmin endpoints, or add cloud storage.
