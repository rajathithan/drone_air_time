# Google Calendar MCP Server — Developer Documentation

A Python-based [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that bridges LLMs and the Google Calendar API. The server exposes calendar operations as MCP tools, accessible via both **stdio** and **SSE** transports, and is backed by a FastAPI HTTP layer.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [MCP Transport Support](#mcp-transport-support)
4. [Setup & Installation](#setup--installation)
5. [Environment Variables Reference](#environment-variables-reference)
6. [Running the Server](#running-the-server)
7. [Source Module Reference](#source-module-reference)
   - [run_server.py](#run_serverpy)
   - [src/auth.py](#srcauthpy)
   - [src/models.py](#srcmodelspy)
   - [src/calendar_actions.py](#srccalendar_actionspy)
   - [src/analysis.py](#srcanalysispy)
   - [src/server.py](#srcserverpy)
   - [src/mcp_bridge.py](#srcmcp_bridgepy)
8. [HTTP API Reference](#http-api-reference)
9. [MCP Tools Reference](#mcp-tools-reference)
10. [MCP Client Configuration](#mcp-client-configuration)
11. [Logging](#logging)
12. [License](#license)

---

## Architecture Overview

```
MCP Client (e.g. Claude Desktop, Cursor)
        │
        │  stdio  OR  SSE (HTTP)
        ▼
  run_server.py  ──────────────────────────────────────────┐
        │  MCP_TRANSPORT=stdio                              │ MCP_TRANSPORT=http
        ▼                                                   ▼
 src/mcp_bridge.py                                   src/server.py
  (FastMCP tools)                               (FastAPI + FastMCP SSE mount)
        │                                                   │
        └──────────── HTTP requests ────────────────────────┘
                             │
                    src/calendar_actions.py
                             │
                    src/analysis.py
                             │
                    Google Calendar API v3
```

**Request flow:**
1. An MCP client invokes a tool (e.g. `find_events`).
2. `mcp_bridge.py` receives the call and makes an HTTP request to the local FastAPI server.
3. `server.py` validates the request, obtains credentials via `auth.py`, and delegates to `calendar_actions.py`.
4. `calendar_actions.py` calls the Google Calendar API and returns a Pydantic model.
5. The response propagates back to the MCP client as a JSON string.

---

## Project Structure

```
calendar-mcp/
├── run_server.py          # Entry point — starts FastAPI and/or MCP stdio server
├── requirements.txt       # Python dependencies
├── .env                   # Local secrets (not committed)
├── .env.example           # Template for .env
├── Dockerfile             # Container definition
├── gcp-oauth-keys.json    # OAuth token storage (auto-generated, not committed)
└── src/
    ├── __init__.py
    ├── auth.py            # Google OAuth 2.0 flow and credential management
    ├── models.py          # Pydantic request/response models
    ├── calendar_actions.py# Google Calendar API action functions
    ├── analysis.py        # Advanced scheduling/analysis logic
    ├── server.py          # FastAPI app, HTTP endpoints, MCP SSE mount
    └── mcp_bridge.py      # MCP tool definitions (delegates to FastAPI)
```

---

## MCP Transport Support

The server supports two transport mechanisms, controlled by environment variables.

### Stdio Transport

| Detail | Value |
|--------|-------|
| Use case | MCP clients that manage the server as a subprocess |
| Env var | `MCP_TRANSPORT=stdio` |
| Communication | stdin / stdout (JSON-RPC) |
| Console logging | Suppressed to keep stdio clean; file logging still active |

When `MCP_TRANSPORT=stdio`, `run_server.py` starts the MCP server in a background thread using `mcp.run(transport='stdio')` and then starts Uvicorn on the configured port so the bridge can make local HTTP calls.

### SSE (HTTP) Transport

| Detail | Value |
|--------|-------|
| Use case | Web clients, remote integrations, or agent frameworks that connect over HTTP |
| Env var | `MCP_TRANSPORT=http` (default) |
| HTTP transport type | Controlled by `MCP_HTTP_TRANSPORT` |
| Default mount path | `/mcp` (override with `MCP_HTTP_MOUNT_PATH`) |

`MCP_HTTP_TRANSPORT` options:

| Value | Behaviour |
|-------|-----------|
| `sse` | Mounts `FastMCP.sse_app()` — SSE endpoint at `/mcp/sse` |
| `streamable-http` | Mounts `FastMCP.streamable_http_app()` |
| `none` / `disabled` / `off` | Disables HTTP MCP transport entirely |

---

## Setup & Installation

### Prerequisites

- Python 3.12+
- A Google Cloud Platform project with the **Google Calendar API** enabled
- Git

### 1. Clone the Repository

```bash
git clone <repository-url>
cd calendar-mcp
```

### 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Google Cloud OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**.
2. Click **+ CREATE CREDENTIALS** → **OAuth client ID** → **Desktop app**.
3. Copy the generated **Client ID** and **Client Secret**.
4. Configure the **OAuth consent screen**:
   - User Type: External
   - Add scope: `https://www.googleapis.com/auth/calendar`
   - Add your Google account as a Test User.
5. Under the credential's **Authorized redirect URIs**, add `http://localhost:8090/` (or the port matching `OAUTH_CALLBACK_PORT`).

### 4. Configure `.env`

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

See [Environment Variables Reference](#environment-variables-reference) for all options.

### 5. Initial Authentication

Run the server once to complete the OAuth browser flow:

```bash
python run_server.py
```

Your browser will open for Google sign-in. After granting access, tokens are saved to `gcp-oauth-keys.json` (or the path set in `TOKEN_FILE_PATH`). Subsequent runs load tokens from disk and refresh automatically.

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | *(required)* | OAuth 2.0 Client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | *(required)* | OAuth 2.0 Client Secret |
| `TOKEN_FILE_PATH` | `./gcp-oauth-keys.json` | Path where OAuth tokens are persisted |
| `CALENDAR_SCOPES` | `https://www.googleapis.com/auth/calendar` | Space-separated OAuth scopes |
| `OAUTH_CALLBACK_PORT` | `8090` | Port for the local OAuth redirect server |
| `CALENDAR_API_BASE_URL` | `http://127.0.0.1:{PORT}` | Base URL the MCP bridge uses to call the FastAPI server |
| `MCP_TRANSPORT` | `http` | Top-level transport: `stdio` or `http` |
| `MCP_HTTP_TRANSPORT` | `sse` | HTTP transport mode: `sse`, `streamable-http`, or `none` |
| `MCP_HTTP_MOUNT_PATH` | `/mcp` | URL prefix where the MCP HTTP app is mounted |
| `MCP_HOST` | `0.0.0.0` | Host for the FastMCP server instance |
| `MCP_DNS_REBINDING_PROTECTION` | `false` | Enable DNS rebinding protection |
| `MCP_ALLOWED_HOSTS` | *(empty)* | Comma-separated list of allowed hosts |
| `MCP_ALLOWED_ORIGINS` | *(empty)* | Comma-separated list of allowed origins |
| `MCP_BRIDGE_HTTP_TIMEOUT_SECONDS` | `60` | Timeout (seconds) for MCP bridge → FastAPI HTTP requests |
| `HOST` | `0.0.0.0` | Uvicorn bind host |
| `PORT` | `8080` | Uvicorn bind port |
| `RELOAD` | `false` | Enable Uvicorn hot-reload (development only) |

---

## Running the Server

### HTTP Mode (default)

```bash
python run_server.py
```

FastAPI starts at `http://localhost:8080`. Interactive API docs available at `http://localhost:8080/docs`.

### Stdio Mode

```bash
MCP_TRANSPORT=stdio python run_server.py
```

The MCP stdio server starts in a background thread; Uvicorn also starts so the bridge can make internal HTTP calls.

### Docker

```bash
docker build -t calendar-mcp .
docker run -p 8080:8080 --env-file .env calendar-mcp
```

---

## Source Module Reference

### `run_server.py`

**Role:** Application entry point.

**Responsibilities:**
- Configures centralised logging (console + rotating file handler at `calendar_mcp.log`).
- Reads `MCP_TRANSPORT` from the environment.
- If `MCP_TRANSPORT=stdio`: spawns `src/mcp_bridge.create_mcp_server()` in a daemon thread via `mcp.run(transport='stdio')` and removes the console log handler to keep stdio clean.
- Always starts Uvicorn (`src.server:app`) on `HOST:PORT`.

**Key environment variables read:** `MCP_TRANSPORT`, `HOST`, `PORT`, `RELOAD`.

---

### `src/auth.py`

**Role:** Google OAuth 2.0 credential management.

#### Configuration constants (loaded from `.env`)

| Constant | Source env var |
|----------|---------------|
| `GOOGLE_CLIENT_ID` | `GOOGLE_CLIENT_ID` |
| `GOOGLE_CLIENT_SECRET` | `GOOGLE_CLIENT_SECRET` |
| `TOKEN_FILE` | `TOKEN_FILE_PATH` |
| `SCOPES` | `CALENDAR_SCOPES` |
| `REDIRECT_PORT` | `OAUTH_CALLBACK_PORT` |

#### `get_credentials() -> Credentials | None`

The primary function used by the rest of the application. Implements a three-stage credential resolution:

1. **Load from file** — reads `TOKEN_FILE` using `Credentials.from_authorized_user_file()`.
2. **Refresh** — if credentials are expired and a refresh token is available, calls `creds.refresh(Request())`.
3. **Full OAuth flow** — if no valid credentials exist, launches `InstalledAppFlow.run_local_server()`:
   - Opens the browser to the Google authorization URL.
   - Starts a temporary local HTTP server on `REDIRECT_PORT` to capture the redirect.
   - Exchanges the authorization code for tokens.
   - Saves tokens to `TOKEN_FILE` as JSON.

Returns `None` if the flow fails.

#### `OAuthCallbackHandler` (internal)

A `SimpleHTTPRequestHandler` subclass that captures the `code` query parameter from Google's OAuth redirect and sets a `threading.Event` to signal the main thread.

---

### `src/models.py`

**Role:** All Pydantic v2 request/response models. All models use `populate_by_name = True` to support both Python-style and Google API camelCase field names.

#### Core Event Models

| Model | Description |
|-------|-------------|
| `EventDateTime` | Wraps `date` (all-day) or `dateTime` + optional `timeZone` |
| `EventAttendee` | Attendee with `email`, `displayName`, `responseStatus`, etc. |
| `EventCreator` | Creator sub-resource from Google Calendar API |
| `EventOrganizer` | Organizer sub-resource |
| `EventReminderOverride` | Single reminder override (`method`, `minutes`) |
| `EventReminders` | `useDefault` flag + list of `EventReminderOverride` |
| `GoogleCalendarEvent` | Full Google Calendar event resource (mirrors API v3 `Events` resource) |

#### Request Models

| Model | Used by endpoint | Required fields |
|-------|-----------------|-----------------|
| `EventCreateRequest` | `POST /calendars/{id}/events` | `summary`, `start`, `end` |
| `QuickAddEventRequest` | `POST /calendars/{id}/events/quickAdd` | `text` |
| `EventUpdateRequest` | `PATCH /calendars/{id}/events/{id}` | *(all optional)* |
| `AddAttendeeRequest` | `POST /calendars/{id}/events/{id}/attendees` | `attendee_emails` |
| `CheckAttendeeStatusRequest` | `POST /events/check_attendee_status` | `event_id` |
| `FreeBusyRequest` | `POST /freeBusy` | `timeMin`, `timeMax`, `items` |
| `ScheduleMutualRequest` | `POST /schedule_mutual` | `attendee_calendar_ids`, `time_min`, `time_max`, `duration_minutes`, `event_details` |
| `ProjectRecurringRequest` | `POST /project_recurring` | `time_min`, `time_max` |
| `AnalyzeBusynessRequest` | `POST /analyze_busyness` | `time_min`, `time_max` |

#### Response Models

| Model | Description |
|-------|-------------|
| `EventsResponse` | Wraps `List[GoogleCalendarEvent]` with pagination tokens |
| `CalendarListEntry` | Single calendar metadata entry |
| `CalendarListResponse` | Wraps `List[CalendarListEntry]` |
| `CheckAttendeeStatusResponse` | `status_map: Dict[email, responseStatus]` |
| `TimePeriod` | `start` / `end` datetime pair |
| `FreeBusyError` | `domain` + `reason` from Google API error |
| `CalendarBusyInfo` | `busy: List[TimePeriod]` + `errors` |
| `FreeBusyResponse` | `timeMin`, `timeMax`, `calendars: Dict[str, CalendarBusyInfo]` |
| `ProjectedEventOccurrenceModel` | Single projected recurrence: `original_event_id`, `original_summary`, `occurrence_start`, `occurrence_end` |
| `ProjectRecurringResponse` | `projected_occurrences: List[ProjectedEventOccurrenceModel]` |
| `DailyBusynessStats` | `event_count`, `total_duration_minutes` |
| `AnalyzeBusynessResponse` | `busyness_by_date: Dict[YYYY-MM-DD, DailyBusynessStats]` |

---

### `src/calendar_actions.py`

**Role:** All direct interactions with the Google Calendar API v3. Each function accepts a `Credentials` object and returns a Pydantic model or `None`/`False` on failure.

#### Helper

| Function | Description |
|----------|-------------|
| `_get_calendar_service(credentials)` | Builds and returns a `googleapiclient` service object for `calendar v3` |

#### Core Calendar Functions

| Function | API call | Returns |
|----------|----------|---------|
| `find_calendars(credentials, min_access_role?)` | `calendarList.list()` | `CalendarListResponse \| None` |
| `create_calendar(credentials, summary)` | `calendars.insert()` | `CalendarListEntry \| None` |
| `find_events(credentials, calendar_id, time_min?, time_max?, query?, max_results, single_events, order_by, ...)` | `events.list()` | `EventsResponse \| None` |
| `create_event(credentials, event_data, calendar_id, send_notifications)` | `events.insert()` | `GoogleCalendarEvent \| None` |
| `quick_add_event(credentials, text, calendar_id, send_notifications)` | `events.quickAdd()` | `GoogleCalendarEvent \| None` |
| `update_event(credentials, event_id, update_data, calendar_id, send_notifications)` | `events.patch()` | `GoogleCalendarEvent \| None` |
| `delete_event(credentials, event_id, calendar_id, send_notifications)` | `events.delete()` | `bool` |
| `add_attendee(credentials, event_id, attendee_emails, calendar_id, send_notifications)` | `events.get()` + `events.patch()` | `GoogleCalendarEvent \| None` |
| `check_attendee_status(credentials, event_id, calendar_id, attendee_emails?)` | `events.get()` | `Dict[str, str] \| None` |
| `find_availability(credentials, time_min, time_max, calendar_ids)` | `freebusy.query()` | `Dict[str, Dict] \| None` |

#### Scheduling Internals

| Function | Description |
|----------|-------------|
| `_merge_intervals(intervals)` | Merges overlapping `{'start': datetime, 'end': datetime}` dicts |
| `_find_first_available_slot(time_min, time_max, duration, busy_intervals, working_hours_start?, working_hours_end?)` | Iterates gaps between merged busy intervals to find the first slot of `duration` that fits; always advances past `now` |
| `find_mutual_availability_and_schedule(credentials, attendee_calendar_ids, time_min, time_max, duration_minutes, event_details, ...)` | Orchestrates `find_availability` → `_merge_intervals` → `_find_first_available_slot` → `create_event` |

#### Analysis Wrappers

| Function | Delegates to |
|----------|-------------|
| `get_projected_recurring_events(...)` | `analysis.project_recurring_events()` |
| `get_busyness_analysis(...)` | `analysis.analyze_busyness()` |

---

### `src/analysis.py`

**Role:** Advanced calendar analysis and recurring event projection. Operates directly on `Credentials`; does not go through the HTTP layer.

#### `ProjectedEventOccurrence`

Plain Python class (not Pydantic) holding a single projected recurrence instance:

| Attribute | Type | Description |
|-----------|------|-------------|
| `original_event_id` | `str` | ID of the master recurring event |
| `original_summary` | `str` | Title of the master event |
| `occurrence_start` | `datetime` | Computed start of this occurrence |
| `occurrence_end` | `datetime` | Computed end (`occurrence_start + duration`) |

#### `project_recurring_events(credentials, time_min, time_max, calendar_id, event_query?) -> List[ProjectedEventOccurrence]`

1. Calls `calendar_actions.find_events()` with `single_events=False` to fetch master recurring event definitions.
2. For each master event, parses `RRULE`, `EXDATE`, and `RDATE` strings from `event.recurrence`.
3. Builds a `dateutil.rrule.rruleset` and calls `ruleset.between(time_min, time_max)` to compute occurrences.
4. Duration is derived from `event.end - event.start`; falls back to 1 hour (timed) or 1 day (all-day).
5. Returns occurrences sorted by `occurrence_start`.

**Note:** `EXDATE` parsing handles `TZID` and `VALUE=DATE` parameters. `RDATE` parsing is stubbed for future implementation.

#### `analyze_busyness(credentials, time_min, time_max, calendar_id) -> Dict[date, Dict[str, Any]]`

1. Calls `calendar_actions.find_events()` with `single_events=True` to get all event instances.
2. Aggregates per calendar-date:
   - `event_count: int` — number of events starting on that date.
   - `total_duration_minutes: float` — sum of durations of timed events.
3. All-day events are counted but contribute `0` to duration.
4. Returns a `dict` sorted by date.

---

### `src/server.py`

**Role:** FastAPI application. Handles HTTP routing, credential management, and mounts the MCP HTTP transport.

#### Application Startup

On startup (`@app.on_event("startup")`), `get_credentials()` is called once and the result is stored in the module-level `global_credentials` variable. All endpoints share this instance.

#### Credential Dependency

`get_current_credentials()` is a FastAPI `Depends` dependency injected into every authenticated endpoint. It:

1. Re-fetches credentials if `global_credentials` is `None`.
2. Attempts `creds.refresh(Request())` if credentials are expired.
3. Falls back to a full re-fetch if refresh fails.
4. Raises `HTTP 503` if credentials cannot be obtained.

#### MCP HTTP Mount

At module load time (before the first request), `create_mcp_server()` is called and the resulting app is mounted based on `MCP_HTTP_TRANSPORT`:

```
GET/POST /mcp/sse         ← SSE endpoint (default)
POST     /mcp/messages    ← SSE message post-back
```

#### Endpoints Summary

See [HTTP API Reference](#http-api-reference) for full details.

---

### `src/mcp_bridge.py`

**Role:** Defines all MCP tools using `FastMCP`. Each tool makes an async HTTP request to the local FastAPI server via `asyncio.to_thread(requests.request, ...)` and returns a JSON string.

#### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CALENDAR_API_BASE_URL` | `http://127.0.0.1:{PORT}` | Base URL for internal FastAPI calls |
| `MCP_BRIDGE_HTTP_TIMEOUT_SECONDS` | `60` | Per-request timeout |

#### `create_mcp_server() -> FastMCP`

Factory function. Creates a `FastMCP("calendar-mcp")` instance with `TransportSecuritySettings` applied, registers all tools, and returns the instance. Called from both `run_server.py` (stdio mode) and `server.py` (HTTP mount).

#### Registered MCP Tools

| Tool name | HTTP call | Description |
|-----------|-----------|-------------|
| `list_calendars` | `GET /calendars` | Lists all calendars |
| `create_calendar` | `POST /calendars` | Creates a new secondary calendar |
| `find_events` | `GET /calendars/{id}/events` | Finds events with optional time range and text search |
| `create_event` | `POST /calendars/{id}/events` | Creates a detailed event with time, description, location, attendees |
| `quick_add_event` | `POST /calendars/{id}/events/quickAdd` | Creates an event from a natural language string |
| `update_event` | `PATCH /calendars/{id}/events/{id}` | Updates event fields (patch semantics) |
| `delete_event` | `DELETE /calendars/{id}/events/{id}` | Deletes an event |
| `add_attendee` | `POST /calendars/{id}/events/{id}/attendees` | Adds attendees to an existing event |
| `check_attendee_status` | `POST /events/check_attendee_status` | Returns each attendee's RSVP status |
| `query_free_busy` | `POST /freeBusy` | Queries busy intervals for multiple calendars |
| `schedule_mutual` | `POST /schedule_mutual` | Finds the first free slot for all attendees and creates the event |
| `analyze_busyness` | `POST /analyze_busyness` | Returns per-day event count and total duration |

All tools return a JSON string. Errors are returned as `{"error": "..."}` rather than raising exceptions.

---

## HTTP API Reference

Base URL: `http://localhost:8080`

Interactive docs: `http://localhost:8080/docs`

### Calendars

| Method | Path | Operation | Description |
|--------|------|-----------|-------------|
| `GET` | `/calendars` | `list_calendars` | List user's calendars |
| `POST` | `/calendars` | `create_calendar` | Create a new calendar |

### Events

| Method | Path | Operation | Description |
|--------|------|-----------|-------------|
| `GET` | `/calendars/{calendar_id}/events` | `find_events` | List/search events |
| `POST` | `/calendars/{calendar_id}/events` | `create_event` | Create a detailed event |
| `POST` | `/calendars/{calendar_id}/events/quickAdd` | `quick_add_event` | Natural language event creation |
| `PATCH` | `/calendars/{calendar_id}/events/{event_id}` | `update_event` | Partial update |
| `DELETE` | `/calendars/{calendar_id}/events/{event_id}` | `delete_event` | Delete event (returns 204) |
| `POST` | `/calendars/{calendar_id}/events/{event_id}/attendees` | `add_attendee` | Add attendees |

### Advanced Scheduling

| Method | Path | Operation | Description |
|--------|------|-----------|-------------|
| `POST` | `/events/check_attendee_status` | `check_attendee_status` | Get RSVP statuses |
| `POST` | `/freeBusy` | `query_free_busy` | Free/busy query |
| `POST` | `/schedule_mutual` | `schedule_mutual` | Auto-schedule meeting (returns 201) |

### Analysis

| Method | Path | Operation | Description |
|--------|------|-----------|-------------|
| `POST` | `/project_recurring` | `project_recurring` | Project recurring event occurrences |
| `POST` | `/analyze_busyness` | `analyze_busyness` | Daily event count/duration stats |

### Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns `{"status": "ok", "authentication": "..."}` |
| `GET` | `/services/offerings` | MCP tool catalog (auto-generated from OpenAPI schema) |

---

## MCP Tools Reference

All tools accept and return plain strings (JSON-encoded). Datetime arguments use ISO 8601 format (e.g. `2026-04-08T09:00:00Z`).

### `list_calendars`
```
min_access_role?: "reader" | "writer" | "owner"
→ CalendarListResponse JSON
```

### `create_calendar`
```
summary: string
→ CalendarListEntry JSON
```

### `find_events`
```
calendar_id: string        # e.g. "primary" or email
time_min?: ISO string
time_max?: ISO string
query?: string
max_results?: int          # default 50
→ EventsResponse JSON
```

### `create_event`
```
calendar_id: string
summary: string
start_time: ISO string     # e.g. "2026-04-08T10:00:00Z"
end_time: ISO string
description?: string
location?: string
attendee_emails?: string[] # list of email addresses
→ GoogleCalendarEvent JSON
```

### `quick_add_event`
```
calendar_id: string
text: string               # e.g. "Lunch with Alice tomorrow at noon"
→ GoogleCalendarEvent JSON
```

### `update_event`
```
calendar_id: string
event_id: string
summary?: string
start_time?: ISO string
end_time?: ISO string
description?: string
location?: string
→ GoogleCalendarEvent JSON
```

### `delete_event`
```
calendar_id: string
event_id: string
→ {"success": "Event successfully deleted."}
```

### `add_attendee`
```
calendar_id: string
event_id: string
attendee_emails: string[]
→ GoogleCalendarEvent JSON
```

### `check_attendee_status`
```
event_id: string
calendar_id?: string       # default "primary"
attendee_emails?: string[] # omit to check all attendees
→ {"status_map": {"user@example.com": "accepted"|"declined"|"tentative"|"needsAction"}}
```

### `query_free_busy`
```
calendar_ids: string[]
time_min: ISO string
time_max: ISO string
→ FreeBusyResponse JSON
```

### `schedule_mutual`
```
attendee_calendar_ids: string[]
time_min: ISO string
time_max: ISO string
duration_minutes: int
summary: string
description?: string
→ GoogleCalendarEvent JSON   # the newly created event
```

### `analyze_busyness`
```
time_min: ISO string
time_max: ISO string
calendar_id?: string         # default "primary"
→ {"busyness_by_date": {"2026-04-08": {"event_count": 3, "total_duration_minutes": 120.0}}}
```

---

## MCP Client Configuration

### Stdio (e.g. Claude Desktop, Cursor)

```json
{
  "mcpServers": {
    "google_calendar": {
      "command": "/path/to/venv/bin/python",
      "args": ["/absolute/path/to/calendar-mcp/run_server.py"],
      "env": {
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

### SSE (remote/HTTP agent frameworks)

```json
{
  "mcpServers": {
    "google_calendar": {
      "command": "/path/to/venv/bin/python",
      "args": ["/absolute/path/to/calendar-mcp/run_server.py"],
      "env": {
        "MCP_TRANSPORT": "http",
        "MCP_HTTP_TRANSPORT": "sse"
      }
    }
  }
}
```

For remote SSE connections where the server is already running, point the client directly at the SSE endpoint:

```
http://your-server:8080/mcp/sse
```

**Important:** Your Google credentials stay in `.env` on the server. Never put them in the MCP client config.

---

## Logging

All logs go to two sinks simultaneously:

| Sink | Location | Level |
|------|----------|-------|
| Console (stderr) | Terminal | `INFO` — suppressed in stdio mode to keep the transport clean |
| File | `calendar_mcp.log` (project root) | `INFO` — always active |

Log format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

Uvicorn access logs are set to `WARNING` to reduce noise; Uvicorn error logs are set to `INFO`.

---

## Deploying to Cloud Run

### Prerequisites

- [Google Cloud SDK (`gcloud`)](https://cloud.google.com/sdk/docs/install) installed and authenticated.
- A GCP project with **Cloud Run**, **Secret Manager**, and **Cloud Build** APIs enabled.
- A service account with the necessary IAM roles (e.g. `roles/secretmanager.secretAccessor`, `roles/run.invoker`).
- Your OAuth token file stored as a Secret Manager secret (e.g. `calendar-oauth-token`).

### Deploy Command

```bash
gcloud run deploy <SERVICE_NAME> \
  --source . \
  --region <REGION> \
  --service-account <SERVICE_ACCOUNT_EMAIL> \
  --set-env-vars GOOGLE_CLIENT_ID=<YOUR_CLIENT_ID>,GOOGLE_CLIENT_SECRET=<YOUR_CLIENT_SECRET>,TOKEN_FILE_PATH=<TOKEN_FILE_PATH> \
  --set-secrets=<SECRET_MOUNT_PATH>=<SECRET_NAME>:latest \
  --allow-unauthenticated
```

### Placeholder Reference

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `<SERVICE_NAME>` | Cloud Run service name | `calendar-mcp` |
| `<REGION>` | GCP region to deploy to | `us-central1` |
| `<SERVICE_ACCOUNT_EMAIL>` | Service account used by the Cloud Run service | `calendar-mcp-sa@my-project.iam.gserviceaccount.com` |
| `<YOUR_CLIENT_ID>` | Google OAuth 2.0 Client ID | *(from Google Cloud Console)* |
| `<YOUR_CLIENT_SECRET>` | Google OAuth 2.0 Client Secret | *(from Google Cloud Console)* |
| `<TOKEN_FILE_PATH>` | Path where the OAuth token is mounted inside the container | `/secrets/gcp-oauth-keys.json` |
| `<SECRET_MOUNT_PATH>` | File path inside the container where the secret is mounted | `/secrets/gcp-oauth-keys.json` |
| `<SECRET_NAME>` | Secret Manager secret name holding the OAuth token JSON | `calendar-oauth-token` |

### Notes

- `--source .` triggers a Cloud Build from the local directory using the `Dockerfile`.
- `--set-secrets` mounts a Secret Manager secret as a file at `<SECRET_MOUNT_PATH>`. The `TOKEN_FILE_PATH` env var must match this mount path so the server can read the token file.
- `--allow-unauthenticated` makes the Cloud Run service publicly accessible. Remove this flag if you want to restrict access to authenticated callers only.
- Sensitive values (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) can also be stored in Secret Manager and injected via `--set-secrets` as environment variables instead of `--set-env-vars` for improved security.

---

## License

This project is dual-licensed:

1. **GNU Affero General Public License v3.0 (AGPL-3.0)** — Free to use, modify, and distribute. Derivative works (including network-deployed modifications) must be released under AGPL-3.0. See the [LICENSE](LICENSE) file.

2. **Commercial License** — Available for proprietary or closed-source use cases where AGPL-3.0 compliance is not feasible. Contact **deciduusleaf@gmail.com** for enquiries.
