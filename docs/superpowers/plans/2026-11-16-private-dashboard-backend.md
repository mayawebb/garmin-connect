# Private Garmin Dashboard Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the existing dashboard with synced Garmin data and OpenAI chat through an email-protected HTTPS link, keeping the database and credentials on the user's Mac.

**Architecture:** Add a FastAPI app serving the static dashboard and three same-origin routes for data, chat, and sync. Reuse the existing Garmin client, SQLite repository, importer, wellness mapping, curated export, and OpenAI client. A launcher runs the app on loopback and Cloudflare Quick Tunnel with an email allowlist.

**Tech Stack:** Python, FastAPI, Uvicorn, existing Requests/OpenAI integration, SQLite, browser JavaScript, Cloudflare Tunnel CLI.

**Spec:** `docs/superpowers/specs/2026-11-16-private-dashboard-backend.md`

## Global Constraints

- Keep Garmin database and both API credentials on the user's Mac.
- The public GitHub Pages site remains a synthetic-data demo.
- Bind the backend to `127.0.0.1` only.
- Do not log prompts, responses, activity details, or credentials.
- OpenAI receives a compact summary and uses `store: false`.
- Garmin data shown is limited to records already synced and future Garmin API responses.
- Keep secrets in `.env`; `.env.example` contains placeholders and `.env` remains ignored.

## Review Focus

- Empty or missing Garmin credentials: sync must return a safe error and not expose key material.
- OpenAI API/network failure: chat returns a safe readable error and never returns a key or upstream body.
- Chart requests whose points are absent from the compact prompt: chat selects an available metric and the server derives points from full local records.
- Missing or sparse health values: export preserves null/missing values and does not create zeros.
- GitHub Pages has no backend: it remains on synthetic sample data and does not make the static public site error.
- Tunnel failure or absent allowlist: launcher must fail closed rather than start an unprotected public service.

---

### Task 1: Backend API and server-side data/chat/sync

**Files:**
- Create: `garmin_dashboard/web.py`
- Modify: `garmin_dashboard/chat.py`
- Create: `garmin_dashboard/chat_context.py`
- Create: `tests/test_web.py`
- Modify: `tests/test_openai_chat.py`
- Modify: `requirements.txt`
- Modify: `garmin_dashboard/static_export.py`

**Interfaces:**
- `create_app(repository=None, garmin_client_factory=None, openai_chat=None)` returns a FastAPI app with injectable dependencies for tests.
- `GET /api/dashboard-data` returns schema version 1, curated `activities` and `health`, `source: "garmin_sqlite"`, and metadata with activity count, date range, and generation time.
- `POST /api/chat` accepts `{question: str, history?: [{role, content}]}` and returns `{answer: str, chart?: {metric, chart_type, group_by}}` using bounded validated history and current DB context.
- `POST /api/sync` runs incremental activity and wellness synchronization and returns activity/wellness imported, skipped, failed counts and safe error summaries.

- [ ] Write tests for dashboard data sourced from the injected SQLite repository, missing values remaining null, chat context/history bounds, and sync report/error behavior.
- [ ] Run `./.venv/bin/python -m pytest tests/test_web.py -q`; expect failures because `garmin_dashboard.web` and FastAPI endpoints are not present.
- [ ] Add FastAPI and Uvicorn dependencies; implement the injected app, curated data payload, chat request validation, and incremental sync route using existing modules.
- [ ] Run `./.venv/bin/python -m pytest tests/test_web.py -q`; expect all endpoint tests to pass without network access or real credentials.

### Task 2: Connect the static dashboard to the backend

**Files:**
- Modify: `static_site/app.js`
- Modify: `static_site/index.html`
- Modify: `static_site/style.css`
- Modify: `tests/static_chat.test.mjs`

**Interfaces:**
- Backend mode is detected by `GET /api/dashboard-data`; the public Pages deployment falls back to existing sample data.
- Backend mode sends chat to `POST /api/chat`, keeps a bounded in-memory conversation, and renders only validated answer/chart data.
- Backend mode exposes a sync button that posts to `/api/sync`, then reloads dashboard data.
- The UI labels API-backed local SQLite data separately from synthetic demo or user-uploaded export data.

- [ ] Add JavaScript tests for preserving backend source metadata and safely handling missing backend/API responses.
- [ ] Run `node --test tests/static_chat.test.mjs`; expect new assertions to fail before frontend integration.
- [ ] Wire backend loading, chat, and sync while preserving sample/export fallback; add sync status and source/date metadata copy.
- [ ] Run `node --test tests/static_chat.test.mjs`; expect all static chat/data tests to pass.

### Task 3: Private HTTPS launcher and setup documentation

**Files:**
- Create: `scripts/run_private_dashboard.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `.gitignore` only if a required local runtime artifact is not already ignored.

**Interfaces:**
- Launcher requires `DASHBOARD_ALLOWED_EMAILS`, `GARMIN_API_KEY`, and `OPENAI_API_KEY`; prints the temporary HTTPS URL, not configuration values.
- Launcher runs Uvicorn on `127.0.0.1` and Cloudflare with `--allowed-mail`; Ctrl-C stops both processes.
- README documents the local Mac requirement, temporary URL lifecycle, email PIN login, and that the Pages URL remains synthetic.

- [ ] Add tests for launcher argument construction, missing allowlist failure, and safe output.
- [ ] Run `./.venv/bin/python -m pytest tests/test_private_launcher.py -q`; expect failures before the launcher exists.
- [ ] Implement the launcher and placeholder-only environment example; document install/start/stop and privacy behavior.
- [ ] Run `./.venv/bin/python -m pytest tests/test_private_launcher.py -q`; expect all launcher tests to pass without starting a real tunnel.

### Task 4: Full verification and review

**Files:**
- Review the complete change set; make fixes only for reproduced issues.

- [ ] Run `./.venv/bin/python -m pytest -q`; expect all Python tests to pass.
- [ ] Run `node --test tests/static_chat.test.mjs`; expect all browser logic tests to pass.
- [ ] Run Python compile checks, JavaScript syntax checks, Git secret/ignore checks, and inspect the final diff.
- [ ] Verify no secrets, database, exports, or user email are in tracked files; confirm the backend binds only to loopback and the static fallback remains intact.
