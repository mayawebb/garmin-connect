# Garmin Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill the wellness data available through the user's Personal API and reorganize the dashboard into Analytics, Health, and saved Training Plans pages.

**Architecture:** Preserve API, storage, and analytics services as page-independent modules. Use `st.navigation` in the entrypoint to dispatch to focused view packages; persist normalized source snapshots and generated plans in SQLite. OpenAI Responses API output is schema-validated before chart rendering or plan storage.

**Tech Stack:** Python, Streamlit, Pandas, Plotly, SQLite, requests, Garmin FIT SDK, Pytest, OpenAI Responses API.

**Spec:** `docs/superpowers/specs/2026-11-12-garmin-dashboard-redesign.md`

## Global Constraints

- Use only documented Garmin Personal API endpoints and verified response shapes.
- Keep credentials server-side and secrets out of logs, UI, and Git.
- Preserve raw API data; never turn absent fields into zero.
- Label all units; default distance to kilometers and running pace to min/km.
- Keep the OpenAI key server-side, send compact data summaries and conversation text with response storage disabled, validate structured output, and never execute model code or SQL.
- Use only records available in the user's account; mark estimates and unavailable metrics.

## Review Focus

- Large wellness date ranges: chunk to fit the sleep endpoint's observed 31-calendar-day window and preserve all chunks.
- Nested HRV response: read records from `hrvSummaries` and extract only present dated numbers.
- Sparse/unsupported health metrics such as VO2 max: render unavailable state rather than a synthetic estimate.
- Short/invalid FIT streams: refuse LT calculation unless the selected, user-designated test has the required duration and HR/speed coverage.
- OpenAI errors or malformed structured output: show a safe error and do not save a partial plan or chart.

---

### Task 1: Chunked Wellness Backfill

**Files:**
- Modify: `garmin_dashboard/wellness.py`
- Test: `tests/test_wellness.py`

**Interfaces:**
- `sync_wellness(client, repository, start_date, end_date)` continues to return a `WellnessSyncReport`; query spans are at most 30 days apart, inclusive, and all payloads are retained by source and span.
- `wellness_metric_points(snapshots)` accepts list payloads and date lists nested under `hrvSummaries` or `data`.

- [ ] Add a test proving a 65-day request calls three bounded spans and stores all three endpoints per span.
- [ ] Add a test proving HRV summaries nested under `hrvSummaries` yield dated numeric points and preserve missing values.
- [ ] Run the focused tests and confirm the new tests fail before implementation.
- [ ] Implement date-window chunking and HRV response flattening.
- [ ] Run focused tests, then backfill the user's wellness data from 2025-10-12 through today; report counts and date bounds without printing raw values.

### Task 2: Navigation and Analytics Page

**Files:**
- Modify: `app.py`
- Create: `garmin_dashboard/views/analytics/__init__.py`
- Create: `garmin_dashboard/views/analytics/page.py`
- Modify: `garmin_dashboard/analytics.py`
- Test: `tests/test_analytics.py`

**Interfaces:**
- `render_analytics(repository, activities)` renders activity charts and the activity chat.
- Analytics helpers produce weekly sport distance, pace trends and sport-specific progression from nullable records.
- LT estimate consumes a selected activity's FIT points only after explicit user confirmation that it was a hard, evenly paced 30-minute test.

- [ ] Test weekly running totals, pace calculations, progression suggestions, and refusing LT estimates without 30 minutes of adequate HR/speed data.
- [ ] Implement the tested helpers and refactor the current UI into the Analytics page.
- [ ] Add measured-data-based summaries for strength, cardio, yoga and other activity types where payload fields exist.
- [ ] Run focused tests and an Analytics page smoke check.

### Task 3: Health Page

**Files:**
- Create: `garmin_dashboard/views/health/__init__.py`
- Create: `garmin_dashboard/views/health/page.py`
- Modify: `app.py`
- Test: `tests/test_health.py`

**Interfaces:**
- `render_health(repository, activities)` charts raw dated wellness metrics, average run HR, resting HR, sleep score, steps, HRV, stress and Body Battery only when present.
- Date selectors and empty states expose actual data coverage.

- [ ] Test extraction/selection of the desired health series with null gaps retained.
- [ ] Build the Health page with trend charts and explicit availability states, including VO2 max.
- [ ] Run focused tests and a Health page smoke check.

### Task 4: Persisted Training Plan Chat

**Files:**
- Modify: `garmin_dashboard/storage.py`
- Modify: `garmin_dashboard/chat.py`
- Create: `garmin_dashboard/views/training_plans/__init__.py`
- Create: `garmin_dashboard/views/training_plans/page.py`
- Modify: `app.py`
- Test: `tests/test_training_plans.py`

**Interfaces:**
- Repository: `save_training_plan(title, goal, content, created_at)` and `list_training_plans()`.
- OpenAI planner returns a validated plan object with goal, duration, weekly sessions, and recovery notes.
- `render_training_plans(repository, activities, wellness_points)` displays goal prompts, generated plans, and saved plans.

- [ ] Test SQLite plan persistence and malformed/unsupported model plans.
- [ ] Implement OpenAI plan generation, shared page launcher, and automatic SQLite saving.
- [ ] Add prompts for 5K/10K/half-marathon goals, lower-HR running, strength, cross-training, and recovery.
- [ ] Run tests and a three-page Streamlit smoke check; verify `.env` and the database remain ignored.

### Task 5: Documentation and Final Verification

**Files:**
- Modify: `README.md`

- [ ] Document page structure, wellness backfill behavior, local chat setup, data limits, and calculated versus Garmin-provided metrics.
- [ ] Run the complete pytest suite, compilation check, and Streamlit smoke checks across all pages.
