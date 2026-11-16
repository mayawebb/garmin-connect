# Training Lab

A Garmin training dashboard with two parts:

- **GitHub Pages site** (`static_site/`) for charts, browser-local data import, training plans, and rule-based chat.
- **Local Streamlit app** for Garmin API synchronization, SQLite storage, and downloading a curated export for Pages.

## GitHub Pages

The Pages site is static and contains only synthetic sample data. It does not sync Garmin, send requests to OpenAI, or contain credentials. To view your own data:

1. Run the local dashboard and sync activities and wellness data.
2. Choose **Download data for website** in the local sidebar.
3. Open the Pages site and choose **Load my export**. The JSON is read in the browser tab; it is not uploaded or saved after closing the tab.
4. Saved training plans are stored in this browser's local storage. They do not include the Garmin export.

To deploy, push to `main`. The GitHub Actions workflow publishes `static_site/` to Pages. On first setup, open **Settings → Pages** in the repository and select **GitHub Actions** as the build and deployment source. After the workflow succeeds, the project site address is usually `https://mayawebb.github.io/garmin-connect/`.

The Pages address is public. The repository contains only code and generated synthetic sample data; never add your export JSON, `.env`, or local database. GitHub Pages is static hosting, so the static version cannot safely keep API credentials or directly provide Garmin sync / OpenAI chat. The local app remains the place to sync Garmin and create the export.

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

For optional OpenAI chat in the local Streamlit app, add `OPENAI_API_KEY` in `.env`. API usage is billed separately from ChatGPT access. The static Pages chat remains local and rule-based.

## Tests

```bash
python -m pytest -q
```

## Architecture

```text
app.py                              Local Streamlit router, sync controls, export
static_site/                        Static GitHub Pages dashboard
.github/workflows/pages.yml         GitHub Pages deployment
garmin_dashboard/
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
```

## Data and units

Distances are shown in kilometers, pace in minutes:seconds per kilometer, elevation in meters, and heart rate in beats per minute. Missing measurements remain unavailable rather than being filled with zero. Treadmill runs are excluded from the dashboard's run analysis. The 5 km equivalent is a rough distance-duration estimate, not a race prediction. Recovery comparisons are descriptive and do not establish cause.

Garmin activity availability and wellness fields depend on the account and API responses. This project uses documented Personal API endpoints and does not assume every activity includes every measurement.
