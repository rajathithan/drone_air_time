import os
import logging

from dotenv import load_dotenv

import google.cloud.logging

from google.adk.agents import LlmAgent
from google.adk.agents import SequentialAgent
from google.adk.agents import ParallelAgent

from .plugins import make_on_model_error_callback
from .tools import geocode_location, get_weather_forecast, firestore_tools, calendar_toolset
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
