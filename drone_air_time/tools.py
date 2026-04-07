import copy
import os
import httpx
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from toolbox_core import ToolboxSyncClient
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams


# --- MCP tool setup ---

def _load_firestore_tools() -> list[Any]:
    """Load Firestore tools from the MCP Toolbox endpoint."""
    firestore_mcp_url = os.getenv("FIRESTORE_MCP_URL")
    logging.info("Connecting to Firestore Toolbox at firestoremcp endpoint.")
    if not firestore_mcp_url:
        logging.warning("FIRESTORE_MCP_URL is not set. Firestore tools disabled.")
        return []
    try:
        firestore_client = ToolboxSyncClient(firestore_mcp_url)
        tools: list[Any] = firestore_client.load_toolset()
        logging.info("Loaded %d Firestore tools.", len(tools))
        return tools
    except Exception as e:
        logging.warning("Failed to connect to Firestore MCP server: %s. Using empty tools list.", str(e))
        return []


def _load_calendar_toolset() -> MCPToolset | None:
    """Load Calendar MCP toolset over SSE after a health check."""
    calendar_mcp_base_url = os.getenv("CALENDAR_MCP_BASE_URL")
    if not calendar_mcp_base_url:
        logging.warning("CALENDAR_MCP_BASE_URL is not set. Calendar tools disabled.")
        return None
    calendar_mcp_base_url = calendar_mcp_base_url.rstrip("/")
    calendar_mcp_health_url = f"{calendar_mcp_base_url}/health"
    calendar_mcp_sse_url = f"{calendar_mcp_base_url}/mcp/sse"
    logging.info("Checking Calendar MCP health endpoint: %s", calendar_mcp_health_url)
    try:
        health_response = httpx.get(calendar_mcp_health_url, timeout=5.0)
        if health_response.status_code == 200:
            logging.info("Calendar MCP health check passed.")
            logging.info("Initializing Calendar MCPToolset over SSE.")
            toolset = MCPToolset(
                connection_params=SseConnectionParams(
                    url=calendar_mcp_sse_url,
                    timeout=15.0,
                    sse_read_timeout=900.0,
                )
            )
            logging.info("Calendar MCPToolset initialized successfully via SSE.")
            return toolset
        else:
            logging.error(
                "Calendar MCP health check failed with status %s. Calendar tools disabled.",
                health_response.status_code,
            )
    except Exception as e:
        logging.error("Failed to initialize Calendar MCPToolset: %s", str(e))
    return None


firestore_tools = _load_firestore_tools()
calendar_toolset = _load_calendar_toolset()


def geocode_location(name: str) -> dict:
    """Search for the latitude, longitude, and timezone of a location by name."""
    logging.info("Geocoding location: %s", name)
    response = httpx.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": name, "count": 1, "language": "en", "format": "json"},
    )
    data = response.json()
    if not data.get("results"):
        logging.warning("Geocoding returned no results for location: %s", name)
    else:
        result = data["results"][0]
        logging.info("Geocoding resolved '%s' to lat=%.4f, lon=%.4f, tz=%s",
                     name, result.get("latitude"), result.get("longitude"), result.get("timezone"))
    return data


# --- Mock weather fallback when Open-Meteo forecast API is unavailable ---
_MOCK_TEMPLATE = {
    "generationtime_ms": 0.0,
    "utc_offset_seconds": -14400,
    "timezone": "America/New_York",
    "timezone_abbreviation": "GMT-4",
    "elevation": 32.0,
    "hourly_units": {
        "time": "iso8601",
        "temperature_2m": "°C",
        "windspeed_10m": "m/s",
        "windspeed_950hPa": "m/s",
        "precipitation_probability": "%",
    },
    "hourly": {
        "temperature_2m": [7.6, 7.0, 5.6, 4.8, 4.3, 3.0, 2.3, 2.0, 3.6, 4.7, 5.5, 6.3,
                           8.1, 9.0, 10.3, 10.8, 11.4, 11.0, 10.5, 9.9, 9.2, 8.0, 7.5, 7.2],
        "windspeed_10m": [3.64, 3.48, 3.81, 4.92, 4.65, 4.12, 3.70, 4.10, 4.60, 4.88, 5.57, 5.02,
                          5.32, 5.20, 4.93, 4.56, 4.66, 4.52, 4.16, 2.60, 2.88, 2.98, 6.18, 2.09],
        "windspeed_950hPa": [11.79, 12.17, 12.45, 13.13, 15.08, 14.67, 13.47, 12.55, 11.30, 9.58, 9.15, 8.14,
                             8.02, 7.86, 7.53, 7.16, 6.77, 7.31, 7.58, 6.42, 8.60, 12.03, 15.25, 10.15],
        "precipitation_probability": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                      0, 0, 0, 1, 1, 2, 2, 2, 2, 11, 11, 11],
    },
}


def _build_mock_weather(latitude: float, longitude: float, date: str, timezone: str) -> dict:
    """Return mock weather data with the target date and coordinates substituted."""
    logging.warning("Building mock weather data for date=%s, tz=%s", date, timezone)
    data = copy.deepcopy(_MOCK_TEMPLATE)
    data["latitude"] = latitude
    data["longitude"] = longitude
    data["timezone"] = timezone
    # Derive utc_offset_seconds and timezone_abbreviation from the timezone string
    try:
        tz = ZoneInfo(timezone)
        dt = datetime.strptime(date, "%Y-%m-%d").replace(hour=12, tzinfo=tz)
        utc_off = dt.utcoffset()
        if utc_off is not None:
            data["utc_offset_seconds"] = int(utc_off.total_seconds())
            data["timezone_abbreviation"] = dt.strftime("%Z") or f"UTC{utc_off}"
    except Exception as e:
        logging.warning("Could not resolve timezone '%s': %s. Using defaults.", timezone, str(e))
    data["mock_data"] = True
    data["mock_notice"] = (
        "Open-Meteo forecast API was unavailable. This is simulated weather data "
        "and does NOT reflect actual conditions. Do not use for real flight decisions."
    )
    # Adjust hourly time stamps to the requested date
    data["hourly"]["time"] = [f"{date}T{h:02d}:00" for h in range(24)]
    return data


def get_weather_forecast(
    latitude: float,
    longitude: float,
    date: str,
    timezone: str,
) -> dict:
    """Get hourly weather forecast data for drone safety analysis at a given location and date."""
    logging.info("Fetching weather forecast for lat=%.4f, lon=%.4f, date=%s, tz=%s",
                 latitude, longitude, date, timezone)
    try:
        response = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "hourly": "temperature_2m,windspeed_10m,windspeed_950hPa,precipitation_probability",
                "start_date": date,
                "end_date": date,
                "windspeed_unit": "ms",
                "timezone": timezone,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            logging.warning("Open-Meteo API returned error: %s. Using mock weather data.",
                            data.get("reason", "unknown"))
            data = _build_mock_weather(latitude, longitude, date, timezone)
        elif "hourly" not in data:
            logging.warning("Weather forecast response missing 'hourly' field for date=%s, lat=%.4f, lon=%.4f",
                            date, latitude, longitude)
            data = _build_mock_weather(latitude, longitude, date, timezone)
        else:
            logging.info("Weather forecast retrieved successfully for date=%s.", date)
    except Exception as e:
        logging.error("Open-Meteo API request failed: %s. Using mock weather data.", str(e))
        data = _build_mock_weather(latitude, longitude, date, timezone)
    # Compute ISO 8601 UTC offset string from utc_offset_seconds so downstream
    # agents can embed it in timestamps without doing timezone math.
    utc_offset_seconds = data.get("utc_offset_seconds", 0)
    sign = "+" if utc_offset_seconds >= 0 else "-"
    abs_seconds = abs(utc_offset_seconds)
    offset_hours = abs_seconds // 3600
    offset_minutes = (abs_seconds % 3600) // 60
    data["utc_offset"] = f"{sign}{offset_hours:02d}:{offset_minutes:02d}"
    logging.info("Computed utc_offset: %s", data["utc_offset"])
    return data
