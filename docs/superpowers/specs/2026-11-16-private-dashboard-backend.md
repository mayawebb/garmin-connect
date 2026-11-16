# Private Garmin Dashboard Backend

## Intent

Serve the existing dashboard with the user's real Garmin history and OpenAI chat through a private HTTPS link. Keep the Garmin database and both API credentials on the user's Mac. The public GitHub Pages site remains a synthetic-data demo.

## Goals

- A same-origin dashboard API provides sanitized activity and wellness data from the local SQLite database.
- Chat answers questions about that data using the existing OpenAI Responses integration and compact data context; the OpenAI key stays server-side.
- A dashboard action can incrementally sync Garmin activity and wellness history using the existing Garmin client and importer.
- Protect the whole private site with Cloudflare email one-time PIN access, allowing only the email already provided by the user.
- Provide a single local start command that starts the private web server and Cloudflare Quick Tunnel and prints the HTTPS URL.

## Non-goals

- Hosting or copying private Garmin data to GitHub Pages or a new cloud database.
- A permanent hostname, always-on hosting, multi-user accounts, new AI features, or race predictions.
- Changing the public Pages demo into a private site.

## Approaches considered

1. **Local FastAPI server behind Cloudflare Quick Tunnel (recommended).** Uses the existing Mac, SQLite database, `.env`, and Cloudflare installation. Email PIN access is provided at the edge. No API key or Garmin record enters browser code or the repository. Tradeoffs: the Mac and tunnel must remain running, and the temporary HTTPS URL changes when restarted.
2. **Hosted private backend.** Can provide a stable link and remain online, but requires choosing and configuring hosting, moving credentials and Garmin data to that service, and operating its storage and access controls. This is more infrastructure than the personal dashboard needs now.
3. **Browser calls to OpenAI/Garmin directly.** Rejected because static browser code cannot protect the API keys and would expose them to anyone with the page.

## Design

- Add a small FastAPI application that serves `static_site/` and same-origin endpoints: `GET /api/dashboard-data`, `POST /api/chat`, and `POST /api/sync`.
- Build the dashboard payload from existing SQLite records through current export/model code; include source and date-range metadata so the UI can identify the data as synced personal records and show its latest recorded date.
- `POST /api/chat` passes the user's question, a bounded recent chat history, and a compact server-generated metric summary into the existing OpenAI client. It returns a readable answer and optional chart data. Do not log prompts, responses, activity details, or credentials.
- `POST /api/sync` runs the existing incremental activity importer and wellness sync; return imported/skipped/failed counts and surface errors without secrets. Do not repeatedly download activity streams.
- Bind the server to `127.0.0.1` only. A launcher reads the allowed email from local environment configuration and runs `cloudflared tunnel --url ... --allowed-mail ...`; the Cloudflare login gate protects all app routes. Configure the given email locally, never commit it.
- The frontend first requests the backend data and calls the backend for chat/sync. On GitHub Pages, where `/api` is absent, it continues to show clearly labeled synthetic sample data and local help text.
- Keep secrets in `.env`, retain `.env.example` placeholders, and keep database/export artifacts ignored by Git.

## Constraints and risks

- Cloudflare Quick Tunnels provide temporary `trycloudflare.com` URLs and are intended for development; the Mac and tunnel process must stay online. This does not deliver an always-on service.
- OpenAI receives the question and a compact summary derived from the user's fitness records. The request will use the repository's existing non-persistent Responses API setting (`store: false`).
- Garmin data available in the dashboard is limited to data already synced into SQLite and to what the Garmin account/API returns during future syncs.
- Browser requests stay same-origin to avoid CORS and cross-site cookie behavior.

## Acceptance checks

- Private tunnel access prompts for email PIN and denies unlisted addresses.
- The private dashboard reports the actual local DB source and date range; the public Pages site remains synthetic.
- Chat uses the server-side OpenAI key and answers open-ended training questions using the user's metrics.
- Sync uses existing Garmin logic and reports activity and wellness results.
- Tests cover backend data/chat/sync behavior with mocked API calls; no real credentials are required for tests.
