# Garmin Training Lab

A local Streamlit dashboard for your Garmin activity and wellness history. It starts with realistic synthetic multi-sport sample activities, so the charts work without Garmin credentials. When configured, it can sync all activity types and available wellness history from Garmin Connect's Personal API into SQLite.

## Dashboard sections

- **Analytics** — weekly outdoor running distance and frequency, median pace, average distance per recorded running week, heart-rate trends, a recorded-effort 5K prediction trend, and strength, cardio, yoga, and Pilates activity trends when source fields are available. Treadmill runs remain in stored activity history but are excluded from running totals, pace analysis, and race estimates. A lactate-threshold field estimate is offered only for a user-selected, confirmed 30-minute test with sufficient heart-rate and speed samples.
- **Health** — recorded resting and activity heart rate, sleep, HRV, steps, stress, Body Battery, and other dated wellness values returned by the API. VO₂ max is displayed only when it exists in the synced data. Recovery signals are shown separately rather than combined into an invented score.
- **Training Plans** — ask the shared chat for running, strength, cross-training, or recovery plans. Validated plans are saved in SQLite and can be reopened later.

The chat launcher sits at the lower right on all three sections. It uses OpenAI's Responses API with structured output so generated charts and plans are validated before display or storage. It sends a compact summary of synced activities and wellness measurements plus your chat messages to OpenAI; Garmin credentials and raw FIT files are not sent. Requests disable response storage. OpenAI API usage is billed separately from ChatGPT Free or subscription access. Suggestions are general training ideas, not medical advice. Cross-metric patterns are exploratory and do not establish that one metric caused another.

## Architecture

```text
app.py                              Streamlit router and sync controls
garmin_dashboard/
  views/analytics/page.py           Training analytics
  views/health/page.py              Wellness and recovery trends
  views/training_plans/page.py      Saved plans
  views/chat_widget.py              Shared floating OpenAI chat launcher
  analytics.py                      Pace, weekly running, and threshold calculations
  health_metrics.py                 Wellness-field selection and run HR series
  config.py                         Environment-based configuration
  models.py                         Validated activity model
  sample_data.py                    Synthetic demo records
  garmin_client.py                  Personal API auth and documented endpoints
  importer.py                       Activity mapping and incremental sync
  wellness.py                       Bounded wellness sync and metric extraction
  activity_streams.py               FIT downloads and sensor records
  chat.py                           Validated OpenAI chart and plan requests
  storage.py                        SQLite activity, wellness, and plan repository
tests/                              Unit tests for models, calculations, sync, and plans
```

Distances are shown in kilometers, running pace in minutes per kilometer, elevation in meters, and heart rate in beats per minute. Missing values remain missing. Imported activity summaries preserve original API fields in SQLite. The API's current account response determines history and metric availability; not every activity has every metric.

## Setup

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run tests

```bash
python -m pytest -q
```

## Launch the dashboard

```bash
streamlit run app.py
```

## Private remote access

For a temporary HTTPS link without moving the SQLite database or Garmin key off this Mac, use a [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) with email PIN access. Install `cloudflared`, start the dashboard, then run the tunnel with an allowed email address:

```bash
streamlit run app.py --server.port 8501 --server.address 127.0.0.1
cloudflared tunnel --url http://127.0.0.1:8501 --allowed-mail you@example.com
```

Share the generated `https://…trycloudflare.com` URL with the allowed email recipient. Cloudflare sends a one-time PIN before allowing access. The URL is temporary and changes when the tunnel restarts; the Mac, dashboard, and tunnel must stay running. Quick Tunnels are intended for testing and demos, not production hosting.

The dashboard starts with generated sample data and needs no credentials. To sync, copy `.env.example` to `.env`, add your Garmin Personal API key to `GARMIN_API_KEY`, launch the app, and select **Sync all activities** in the sidebar. Choose a wellness date range and select **Sync wellness history**. The wellness importer breaks large requests into bounded date windows for the sleep endpoint and stores each endpoint's original response. The key is read only by Python server-side code; it is never displayed in the dashboard. `.env` and local SQLite files are excluded from Git. `.env.example` contains placeholders only.

For chat, add your OpenAI API key to `OPENAI_API_KEY` in `.env`. The default model is `gpt-5.4-mini`; override it with `OPENAI_MODEL`. Restart Streamlit after changing `.env`. An OpenAI API key and API billing are separate from ChatGPT Free access.

The first activity sync requests summaries of every type and follows the documented `start`/`limit` pagination parameters. Subsequent activity syncs use the latest stored date with a one-day overlap to catch late or changed summaries. Wellness sync saves Garmin's original JSON by endpoint and date range and charts dated numeric values that are present. FIT files are cached per activity in SQLite to avoid repeat downloads. The 5K estimate applies the Riegel distance-duration formula (exponent 1.06) to each outdoor run at least 2 km long; recorded training effort may not represent race effort. The lactate-threshold calculation is a pace/heart-rate field estimate, not a lab measurement; it is not saved as a Garmin-provided metric. Garmin's Personal API Swagger lists a fitness-age endpoint but no VO2 max endpoint, and the synced payloads contained no VO2 max field. Availability of historical activities, daily metrics, and detailed sensor streams depends on the account and API response.

## Garmin API references

- [Garmin Connect Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api/)
- [Personal API FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/)
- [Personal API Swagger documentation](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/)
- [Garmin-maintained Python reference client](https://github.com/garmin/connect-personal-api-python)

The client uses only documented endpoints. Token lifetime is 24 hours or until the key expires; Garmin documents no refresh tokens, so the app obtains a new access token from the key as needed. API responses may omit individual measurements; missing values are preserved as `NULL` in SQLite. Historical coverage and detailed measurement availability must be confirmed against the API and account.
