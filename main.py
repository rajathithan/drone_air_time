from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, model_validator
from typing import Optional
from datetime import datetime, timedelta, date
import uuid
import uvicorn
import json
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from drone_air_time.agent import root_agent

app = FastAPI(title="Drone Flight Time API", version="1.0.0")

session_service = InMemorySessionService()
runner = Runner(agent=root_agent, app_name="drone_air_time", session_service=session_service)

class DroneRequest(BaseModel):
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    date: date

    @model_validator(mode='after')
    def check_location_or_coords(self) -> 'DroneRequest':
        has_location = self.location is not None
        has_coords = self.latitude is not None and self.longitude is not None
        if not has_location and not has_coords:
            raise ValueError("Either 'location' or both 'latitude' and 'longitude' must be provided")
        if self.latitude is not None and self.longitude is None:
            raise ValueError("'longitude' is required when 'latitude' is provided")
        if self.longitude is not None and self.latitude is None:
            raise ValueError("'latitude' is required when 'longitude' is provided")
        return self

class DroneResponse(BaseModel):
    status: str
    request_summary: dict
    workflow_audit: dict
    safety_reasoning: str


@app.get("/")
async def home():
    return {
        "message": "Welcome to Drone Flight Time API",
        "agents": [
            {
                "name": "OpenMeteo_Sensor",
                "functionality": "Fetches location-aware weather telemetry for flight planning.",
            },
            {
                "name": "Firestore_Archivist",
                "functionality": "Archives raw weather telemetry for audit and traceability.",
            },
            {
                "name": "Analyzer_Agent",
                "functionality": "Evaluates weather safety thresholds and identifies optimal 2-hour windows.",
            },
            {
                "name": "Calendar_Scheduler",
                "functionality": "Schedules approved drone windows in calendar via MCP tools.",
            },
            {
                "name": "Response_Formatter",
                "functionality": "Formats final orchestration output into API-compatible JSON schema.",
            },
        ],
        "post_endpoint": {
            "path": "/v1/drone-air-time",
            "method": "POST",
            "description": "Run end-to-end drone flight safety analysis and scheduling workflow.",
            "required": "Provide either location OR both latitude and longitude, plus date.",
            "sample_request": {
                "location": "Chennai",
                "date": "2026-04-06",
            },
            "sample_request_with_coordinates": {
                "latitude": 13.0827,
                "longitude": 80.2707,
                "date": "2026-04-06",
            },
        },
        "swagger_docs": "/docs",
    }


def _parse_agent_json_response(text: str) -> dict | None:
    """Parse agent output as JSON, with a fallback for wrapped markdown/text."""
    if not text:
        return None

    # First try direct JSON parsing.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: extract the first top-level JSON object if text contains wrappers.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None
    return None

@app.post("/v1/drone-air-time", response_model=DroneResponse)
async def schedule_drone_flight(request: DroneRequest):
    # Validate date is within 5 days
    today = datetime.now().date()
    if request.date > today + timedelta(days=5):
        raise HTTPException(status_code=400, detail="Date requested is more than 5 days in the future")

    user_id = "drone_user"
    session_id = str(uuid.uuid4())
    try:
        await session_service.create_session(
            app_name="drone_air_time", user_id=user_id, session_id=session_id
        )
        if request.latitude is not None and request.longitude is not None:
            location_part = f"coordinates: latitude={request.latitude}, longitude={request.longitude}"
            if request.location:
                location_part += f" (label: {request.location})"
        else:
            location_part = f"location: {request.location}"
        content = types.Content(
            role='user',
            parts=[types.Part(text=f"Schedule drone flight for {location_part}, date: {request.date.isoformat()}")]
        )
        final_response_text = None
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_response_text = (event.content.parts[0].text or "").strip()
        if not final_response_text:
            raise HTTPException(status_code=500, detail="Agent returned no response")

        parsed = _parse_agent_json_response(final_response_text)
        if parsed is None:
            # Return a structured non-500 response when the agent emits non-JSON text.
            return DroneResponse(
                status="FAILED",
                request_summary={
                    "location": request.location,
                    "latitude": request.latitude,
                    "longitude": request.longitude,
                    "date": request.date.isoformat(),
                },
                workflow_audit={
                    "error_code": "NON_JSON_AGENT_RESPONSE",
                    "raw_response": final_response_text,
                },
                safety_reasoning="Agent response was not valid JSON. Check agent prompts to enforce JSON-only output.",
            )

        result = parsed
        return DroneResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":    
    uvicorn.run(app, host="0.0.0.0", port=8000)