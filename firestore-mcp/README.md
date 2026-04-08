# Firestore MCP Toolbox

MCP Toolbox server that exposes a Firestore write tool for archiving [Open-Meteo](https://open-meteo.com/) weather data. An upstream ADK agent fetches hourly forecasts from the Open-Meteo API and stores them via this toolbox into a Firestore collection.

## Prerequisites

- **Google Cloud project** with Firestore enabled
- **Firestore database** named `openmateodata` (Native mode)
- **`toolbox` binary** (v0.31.0+) — download from [googleapis/genai-toolbox releases](https://github.com/googleapis/genai-toolbox/releases)
- **GCP authentication** configured (Application Default Credentials or a service account)

## Installing the Toolbox Binary

Download the latest `toolbox` binary from [MCP Toolbox for Databases](https://github.com/googleapis/genai-toolbox/releases).

### macOS (Apple Silicon)

```bash
curl -LO https://github.com/googleapis/genai-toolbox/releases/latest/download/toolbox-darwin-arm64
mv toolbox-darwin-arm64 toolbox
chmod +x toolbox
```

### macOS (Intel)

```bash
curl -LO https://github.com/googleapis/genai-toolbox/releases/latest/download/toolbox-darwin-amd64
mv toolbox-darwin-amd64 toolbox
chmod +x toolbox
```

### Linux (x86_64)

```bash
curl -LO https://github.com/googleapis/genai-toolbox/releases/latest/download/toolbox-linux-amd64
mv toolbox-linux-amd64 toolbox
chmod +x toolbox
```

### Linux (ARM64)

```bash
curl -LO https://github.com/googleapis/genai-toolbox/releases/latest/download/toolbox-linux-arm64
mv toolbox-linux-arm64 toolbox
chmod +x toolbox
```

### Verify installation

```bash
./toolbox --version
```

> **Minimum version:** v0.31.0 is required. Earlier versions use different flags and may not support `firestore-add-documents`.

## Project Structure

```
.
├── Dockerfile      # Container image for deploying the toolbox
├── toolbox         # genai-toolbox binary
├── tools.yaml      # Source, tool, and toolset configuration
└── README.md
```

## Configuration

### `tools.yaml`

```yaml
sources:
  firestore-source:
    kind: firestore
    project: <your-gcp-project-id>
    database: <your-firestore-database-name>

tools:
  archive_data_to_firestore:
    kind: firestore-add-documents
    source: firestore-source
    description: >-
      Archives OpenMeteo weather data to Firestore. The agent must pass
      collectionPath as 'lat_long_day_wise_data' and the complete weather
      API response JSON as documentData. The documentData should contain
      latitude, longitude, timezone, elevation, hourly_units, and hourly
      fields with arrays for time, temperature_2m, windspeed_10m,
      windspeed_950hPa, and precipitation_probability.

toolsets:
  my_firestore_toolset:
    - archive_data_to_firestore
```

| Section | Key | Description |
|---------|-----|-------------|
| `sources.firestore-source` | `kind` | Must be `firestore` |
| | `project` | GCP project ID |
| | `database` | Firestore database name (`openmateodata`) |
| `tools.archive_data_to_firestore` | `kind` | `firestore-add-documents` — built-in tool type for inserting documents |
| | `source` | References the source defined above |

### Tool Parameters

The `firestore-add-documents` tool exposes three **built-in** parameters (not declared in the YAML):

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `collectionPath` | `string` | Yes | Relative collection path. Agents should pass `"lat_long_day_wise_data"`. |
| `documentData` | `object` | Yes | The document payload. Accepts raw JSON — the toolbox converts it to Firestore's typed format internally. |
| `returnData` | `boolean` | No | Default `false`. Set `true` to return the created document in the response. |

## Running Locally

### Start the server

```bash
./toolbox --config tools.yaml --port 8000 --ui --enable-api
```

| Flag | Purpose |
|------|---------|
| `--config` | Path to the YAML config file |
| `--port` | Listening port |
| `--ui` | Enables the web UI at `/ui` |
| `--enable-api` | Enables the REST `/api` endpoints (required for the UI to work) |

Once started, the following endpoints are available:

| Endpoint | Protocol | Description |
|----------|----------|-------------|
| `http://127.0.0.1:8000/` | HTTP | Health check |
| `http://127.0.0.1:8000/ui` | HTTP | Web UI for inspecting tools |
| `http://127.0.0.1:8000/api/toolset/` | REST | List tools and parameters |
| `http://127.0.0.1:8000/mcp` | JSON-RPC | MCP endpoint for agent connections |

### Verify the tool is registered

```bash
curl -s http://127.0.0.1:8000/api/toolset/ | python3 -m json.tool
```

## Docker

### Build

```bash
docker build -t firestore-mcptoolbox .
```

### Run

```bash
docker run -p 8080:8080 \
  -v "$HOME/.config/gcloud:/root/.config/gcloud:ro" \
  firestore-mcptoolbox
```

The container listens on port `8080` with `--address 0.0.0.0`, `--ui`, and `--enable-api` enabled by default (see `Dockerfile`).

> **Note:** Mount your GCP credentials or attach a service account when deploying to Cloud Run / GKE.

## Agent Integration

The upstream Open-Meteo ADK agent should invoke `archive_data_to_firestore` with:

```json
{
  "collectionPath": "lat_long_day_wise_data",
  "documentData": {
    "latitude": 40.710335,
    "longitude": -73.99308,
    "generationtime_ms": 2.25,
    "utc_offset_seconds": -14400,
    "timezone": "America/New_York",
    "timezone_abbreviation": "GMT-4",
    "elevation": 32.0,
    "hourly_units": {
      "time": "iso8601",
      "temperature_2m": "°C",
      "windspeed_10m": "m/s",
      "windspeed_950hPa": "m/s",
      "precipitation_probability": "%"
    },
    "hourly": {
      "time": ["2026-04-06T00:00", "2026-04-06T01:00"],
      "temperature_2m": [7.6, 7.0],
      "windspeed_10m": [3.64, 3.48],
      "windspeed_950hPa": [11.79, 12.17],
      "precipitation_probability": [0, 0]
    }
  },
  "returnData": false
}
```

### Data source

The weather data originates from the Open-Meteo Forecast API:

```
https://api.open-meteo.com/v1/forecast?latitude=40.7128&longitude=-74.0060&hourly=temperature_2m,windspeed_10m,windspeed_950hPa,precipitation_probability&start_date=2026-04-06&end_date=2026-04-06&windspeed_unit=ms&timezone=America%2FNew_York
```

### Firestore document structure

Each document stored in `lat_long_day_wise_data` contains the full API response, including:

- `latitude`, `longitude`, `elevation` — location metadata
- `timezone`, `utc_offset_seconds` — time zone info
- `hourly_units` — unit labels for each metric
- `hourly` — arrays of 24 hourly values for `time`, `temperature_2m`, `windspeed_10m`, `windspeed_950hPa`, `precipitation_probability`

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `HTTP 404` on `/api/toolset/` | API endpoints disabled by default in v0.31.0+ | Add `--enable-api` flag |
| `bind: address already in use` | Previous toolbox instance still running | `lsof -ti:<port> \| xargs kill -9` then restart |
| `--tools-file` deprecation warning | Flag renamed in v0.31.0 | Use `--config` instead |
| Firestore permission errors | Missing or invalid GCP credentials | Run `gcloud auth application-default login` or mount a service account key |

## References

- [genai-toolbox](https://github.com/googleapis/genai-toolbox)
- [Firestore source](https://github.com/googleapis/genai-toolbox/tree/main/internal/sources/firestore)
- [firestore-add-documents tool](https://github.com/googleapis/genai-toolbox/tree/main/internal/tools/firestore/firestoreadddocuments)
- [Open-Meteo API docs](https://open-meteo.com/en/docs)
