# Training Lab

A Garmin training dashboard with a public demo and a private local service:

- **Private dashboard** (`garmin_dashboard/web.py`) serves the existing charts from your Mac, reads your SQLite history, sends chat requests to OpenAI from the server, and can sync Garmin.
- **GitHub Pages site** (`static_site/`) is a public synthetic-data demo. It has no access to your `.env`, Garmin account, or SQLite database.
- **Local Streamlit app** remains available for manual Garmin synchronization, SQLite inspection, and curated data export.

## Shareable private dashboard link

Open the stable link: **https://mayawebb.github.io/garmin-connect/private/**. It redirects to the current live dashboard and then asks for an email PIN. The shortcut is shareable, but only addresses in `DASHBOARD_ALLOWED_EMAILS` can sign in.

GitHub Pages cannot read the Mac's `.env` or SQLite database. The private link reaches the real Garmin data through the local API on this Mac, exposed over an email-restricted Cloudflare Quick Tunnel. No domain purchase or Cloudflare account setup is needed. The Mac, dashboard server, and tunnel must stay running; start them with:

```bash
source .venv/bin/activate
python scripts/run_private_dashboard.py
```

The launcher updates the Pages shortcut automatically whenever the tunnel URL changes. It uses the GitHub CLI, so run `gh auth login` once if it is not already signed in. If the Mac is asleep or the command is stopped, the shortcut explains how to start it again. The public Pages demo at the root remains synthetic sample data.

Install Cloudflare Tunnel if needed (`brew install cloudflared`).

## Public GitHub Pages demo

The Pages site is static and contains only synthetic sample data. It does not sync Garmin, send requests to OpenAI, or contain credentials. Its chat uses local rules. To view your own data privately, use the local backend below. You can also:

1. Run the local dashboard and sync activities and wellness data.
2. Choose **Download data for website** in the local sidebar.
3. Open the Pages site and choose **Load my export**. The JSON is read in the browser tab; it is not uploaded or saved after closing the tab.
4. Saved training plans are stored in this browser's local storage. They do not include the Garmin export.

The site starts with clearly labeled synthetic sample data. A number such as “28 runs” is demo data until you load your own export. The export contains records already synced into your local SQLite database; it does not make a live Garmin API connection from GitHub Pages.

The site is published from the `main` branch. The repository root forwards to `static_site/`, so `https://mayawebb.github.io/garmin-connect/` is the public demo link. It does not show your personal history.

The Pages address is public. The repository contains only code and generated synthetic sample data; never add your export JSON, `.env`, or local database. A push to `main` publishes the public demo.

## Run the local Garmin app

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Add your Garmin Personal API key to `GARMIN_API_KEY` in `.env`, then run:

```bash
streamlit run app.py
```

The local app also starts with synthetic sample activities if no records are stored. Select **Sync all activities** and **Sync wellness history** to retrieve account data. `.env`, SQLite databases, and `data/` are excluded from Git. Never commit an export downloaded from the dashboard.

For optional OpenAI chat in the local Streamlit app, add `OPENAI_API_KEY` in `.env`. API usage is billed separately from ChatGPT access.

## Local-only Garmin app

For direct local access, run `streamlit run app.py`. The shareable private link above uses the same `.env` and SQLite database through the protected local API.

## Tests

```bash
python -m pytest -q
node --test tests/static_chat.test.mjs
```

## Architecture

```text
app.py                              Local Streamlit router, sync controls, export
static_site/                        GitHub Pages demo and private dashboard UI
index.html                          Redirects the Pages root to the dashboard
garmin_dashboard/
  web.py                            Private FastAPI server and same-origin API
  chat_context.py                   Shared compact metric context for chat
  views/analytics/page.py           Local training analytics
  views/health/page.py              Local wellness trends
  views/training_plans/page.py      Local saved plans
  static_export.py                  Curated, identifier-free JSON export
  analytics.py                      Running calculations and pace formatting
  health_metrics.py                 Curated wellness metrics
  garmin_client.py                  Garmin Personal API client
  importer.py                       Activity synchronization
  wellness.py                       Wellness sync and extraction
  storage.py                        SQLite persistence
tests/                              Unit tests
scripts/run_private_dashboard.py   Local API and email-protected Quick Tunnel launcher
```

## Data and units

Distances are shown in kilometers, pace in minutes:seconds per kilometer, elevation in meters, and heart rate in beats per minute. Missing measurements remain unavailable rather than being filled with zero. Treadmill runs are excluded from the dashboard's run analysis. The 5 km equivalent is a rough distance-duration estimate, not a race prediction. Recovery comparisons are descriptive and do not establish cause.

Garmin activity availability and wellness fields depend on the account and API responses. This project uses documented Personal API endpoints and does not assume every activity includes every measurement.
