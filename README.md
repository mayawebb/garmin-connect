# Training Lab

A Garmin training dashboard with a public demo and a private local service:

- **Private dashboard** (`garmin_dashboard/web.py`) serves the existing charts from your Mac, reads your SQLite history, sends chat requests to OpenAI from the server, and can sync Garmin.
- **GitHub Pages site** (`static_site/`) is a public synthetic-data demo. It has no access to your `.env`, Garmin account, or SQLite database.
- **Local Streamlit app** remains available for manual Garmin synchronization, SQLite inspection, and curated data export.

## GitHub Pages

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

## Open the private HTTPS dashboard

The private dashboard runs on this Mac and uses the same `.env` and SQLite data as the local app. Cloudflare Quick Tunnel supplies a temporary HTTPS link and sends a one-time PIN to each allowed email. The Mac and this command must stay running while the link is in use; the link changes when you restart it.

1. Make sure `.env` has `GARMIN_API_KEY` and `OPENAI_API_KEY`. Set `DASHBOARD_ALLOWED_EMAILS` to the email address allowed to sign in. Separate multiple allowed addresses with commas.
2. Install Cloudflare Tunnel if needed. On macOS with Homebrew: `brew install cloudflared`.
3. Start the private service:

   ```bash
   source .venv/bin/activate
   python scripts/run_private_dashboard.py
   ```

4. Open the `https://…trycloudflare.com` link printed in the terminal. Enter the one-time PIN sent to an allowed email.
5. Select **Sync Garmin** in the dashboard to update activities and recent wellness data. The dashboard shows separate activity and wellness date ranges and the number of stored records.

Press `Ctrl+C` in the terminal to stop the server and tunnel. The local service binds to `127.0.0.1`; only the authenticated Cloudflare tunnel exposes it. OpenAI receives your question and a compact summary of synced metrics; the key stays on this Mac and API requests use `store: false`. Cloudflare Quick Tunnels are temporary and intended for development, so this is not an always-on, permanent link.

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
