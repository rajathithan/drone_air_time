from google.adk.agents import LlmAgent
from google.adk.agents import SequentialAgent
from google.adk.agents import ParallelAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
from dotenv import load_dotenv
from toolbox_core import ToolboxSyncClient
from typing import Any
import os
import logging
import httpx
import google.cloud.logging

from .plugins import make_on_model_error_callback
from .prompts import open_meteo as open_meteo_prompt
from .prompts import firestore as firestore_prompt
from .prompts import analyzer as analyzer_prompt
from .prompts import calendar as calendar_prompt
from .prompts import response_formatter as response_formatter_prompt

cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()
logging.info("Cloud Logging initialized.")

load_dotenv()

model_name = os.getenv("MODEL", "gemini-2.5-flash")
logging.info("Using model: %s", model_name)

firestore_mcp_url = os.getenv("FIRESTORE_MCP_URL")
calendar_mcp_base_url = os.getenv("CALENDAR_MCP_BASE_URL")

calendar_mcp_health_url = None
calendar_mcp_sse_url = None
if calendar_mcp_base_url:
    calendar_mcp_base_url = calendar_mcp_base_url.rstrip("/")
    calendar_mcp_health_url = f"{calendar_mcp_base_url}/health"
    calendar_mcp_sse_url = f"{calendar_mcp_base_url}/mcp/sse"

# Setup MCP tools
logging.info("Connecting to Firestore Toolbox at firestoremcp endpoint.")
if not firestore_mcp_url:
    logging.warning("FIRESTORE_MCP_URL is not set. Firestore tools disabled.")
    firestore_tools: list[Any] = []
else:
    try:
        firestore_client = ToolboxSyncClient(firestore_mcp_url)
        firestore_tools: list[Any] = firestore_client.load_toolset()
        logging.info("Loaded %d Firestore tools.", len(firestore_tools))
    except Exception as e:
        logging.warning("Failed to connect to Firestore MCP server: %s. Using empty tools list.", str(e))
        firestore_tools: list[Any] = []

calendar_toolset = None
if not calendar_mcp_health_url or not calendar_mcp_sse_url:
    logging.warning("CALENDAR_MCP_BASE_URL is not set. Calendar tools disabled.")
else:
    logging.info("Checking Calendar MCP health endpoint: %s", calendar_mcp_health_url)
    try:
        health_response = httpx.get(calendar_mcp_health_url, timeout=5.0)
        if health_response.status_code == 200:
            logging.info("Calendar MCP health check passed.")
            logging.info("Initializing Calendar MCPToolset over SSE.")
            calendar_toolset = MCPToolset(
                connection_params=SseConnectionParams(
                    url=calendar_mcp_sse_url,
                    timeout=15.0,
                    sse_read_timeout=900.0,
                )
            )
            logging.info("Calendar MCPToolset initialized successfully via SSE.")
        else:
            logging.error(
                "Calendar MCP health check failed with status %s. Calendar tools disabled.",
                health_response.status_code,
            )
    except Exception as e:
        logging.error("Failed to initialize Calendar MCPToolset: %s", str(e))

# Plain Python function tools for Open-Meteo REST calls
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


def get_weather_forecast(
    latitude: float,
    longitude: float,
    date: str,
    timezone: str,
) -> dict:
    """Get hourly weather forecast data for drone safety analysis at a given location and date."""
    logging.info("Fetching weather forecast for lat=%.4f, lon=%.4f, date=%s, tz=%s",
                 latitude, longitude, date, timezone)
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
    )
    data = response.json()
    if "hourly" not in data:
        logging.warning("Weather forecast response missing 'hourly' field for date=%s, lat=%.4f, lon=%.4f",
                        date, latitude, longitude)
    else:
        logging.info("Weather forecast retrieved successfully for date=%s.", date)
    return data

open_meteo_agent = LlmAgent(
    name='OpenMeteo_Sensor',
    description='Atmospheric Data Specialist',
    output_key="weather_data",
    tools=[geocode_location, get_weather_forecast],
    instruction=open_meteo_prompt.INSTRUCTION,
    on_model_error_callback=make_on_model_error_callback("[OpenMeteo] Quota exhausted. Unable to retrieve weather data."),
)

firestore_agent = LlmAgent(
    name='Firestore_Archivist',
    description='Data Persistence & Compliance Specialist',
    output_key="archive_status",
    tools=firestore_tools,
    instruction=firestore_prompt.INSTRUCTION,
    on_model_error_callback=make_on_model_error_callback("[Firestore] Quota exhausted. Unable to archive weather data."),
)

analyzer_agent = LlmAgent(
    name='Analyzer_Agent',
    description='Logic-engine that scans data for a 2-hour window meeting safety thresholds',
    output_key="analysis_result",
    instruction=analyzer_prompt.INSTRUCTION,
    on_model_error_callback=make_on_model_error_callback("[Analyzer] Quota exhausted. Unable to analyze weather data."),
)

calendar_agent = LlmAgent(
    name='Calendar_Scheduler',
    description='Scheduling & Logistics Specialist',
    output_key="calendar_status",
    tools=[calendar_toolset] if calendar_toolset is not None else [],
    instruction=calendar_prompt.INSTRUCTION,
    on_model_error_callback=make_on_model_error_callback("[Calendar] Quota exhausted. Unable to schedule flight."),
)

response_formatter_agent = LlmAgent(
    name='Response_Formatter',
    description='Final API Response Formatter',
    output_key="final_response",
    instruction=response_formatter_prompt.INSTRUCTION,
    on_model_error_callback=make_on_model_error_callback(
        "{\"status\":\"FAILED\",\"request_summary\":{},\"workflow_audit\":{\"error\":\"Formatter quota exhausted\"},\"safety_reasoning\":\"Unable to format final response due to model quota limits.\"}"
    ),
)

parallel_agent = ParallelAgent(
    name='Parallel_Processor',
    sub_agents=[firestore_agent, analyzer_agent],
)

root_agent = SequentialAgent(
    name='Main_Orchestrator',
    description='Chief Logistics & Coordination Officer',
    sub_agents=[open_meteo_agent, parallel_agent, calendar_agent, response_formatter_agent],
)
