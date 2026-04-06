# Drone Flight Safety API

The Drone Flight Safety API is an autonomous flight scheduling system. It receives a location and date, fetches high-altitude weather telemetry, archives the data for safety audits, identifies the safest flight window, and reserves that time in the user's Google Calendar.

## Overview

This API leverages Google ADK (Agent Development Kit) agents orchestrated through FastAPI to provide intelligent drone flight planning. It integrates with external services via MCP tools for weather forecasting, data persistence, and calendar scheduling.

## Features

- **Weather Analysis**: Fetches and analyzes weather data for flight safety assessment
- **Data Archiving**: Automatically archives flight analysis results to Google Cloud Firestore
- **Flight Scheduling**: Integrates with Google Calendar to schedule safe flight windows
- **AI-Powered Agents**: Uses specialized agents for each aspect of flight planning
- **RESTful API**: Built with FastAPI for high-performance, asynchronous operations
- **Containerized Deployment**: Ready for deployment on Google Cloud Run via Docker

## Architecture

The system uses a sequential agent orchestration pattern with five specialized agents:

### Agents

1. **Open-Meteo Agent** (`open_meteo_agent`)
   - **Functionality**: Retrieves weather forecast data from the Open-Meteo API
   - **Input**: Location coordinates (latitude, longitude), date range
   - **Output**: Structured weather data including temperature, wind speed, precipitation, and visibility
   - **Purpose**: Provides raw weather data for safety analysis

2. **Analyzer Agent** (`analyzer_agent`)
   - **Functionality**: Analyzes weather conditions against drone flight safety criteria
   - **Input**: Weather data from Open-Meteo agent
   - **Output**: Safety assessment with risk levels and recommendations
   - **Purpose**: Determines if weather conditions are safe for drone operations

3. **Firestore Agent** (`firestore_agent`)
   - **Functionality**: Archives flight analysis results to Google Cloud Firestore
   - **Input**: Analysis results and metadata
   - **Output**: Confirmation of data storage
   - **Purpose**: Maintains historical records of flight safety assessments

4. **Calendar Agent** (`calendar_agent`)
   - **Functionality**: Schedules optimal flight windows in Google Calendar
   - **Input**: Safe flight time recommendations
   - **Output**: Calendar event creation confirmation
   - **Purpose**: Automates flight planning and scheduling

5. **Response Formatter Agent** (`response_formatter_agent`)
   - **Functionality**: Formats the final API response in a consistent structure
   - **Input**: Outputs from all previous agents
   - **Output**: Structured JSON response with all analysis data
   - **Purpose**: Ensures consistent API response format

### Agent Orchestration

Agents are orchestrated using Google ADK's `SequentialAgent`, executing in the following order:
1. Open-Meteo → 2. Analyzer → 3. Firestore → 4. Calendar → 5. Response Formatter

Each agent includes error handling and fallback mechanisms for robust operation.

## API Endpoints

### GET /
- **Description**: Health check and API information
- **Response**: Welcome message with API status

### POST /v1/drone-air-time
- **Description**: Main endpoint for drone flight safety analysis
- **Request Body**:
  ```json
  {
    "location": {
      "latitude": float,
      "longitude": float
    },
    "date": "YYYY-MM-DD",
    "drone_type": "string (optional)",
    "flight_duration_hours": int (optional)
  }
  ```
- **Response**:
  ```json
  {
    "flight_id": "string",
    "location": {...},
    "weather_analysis": {...},
    "safety_assessment": {...},
    "recommended_windows": [...],
    "archived": boolean,
    "scheduled": boolean
  }
  ```
- **Error Responses**: 400 (Bad Request), 500 (Internal Server Error)

## Setup and Installation

### Prerequisites
- Python 3.11+
- Google Cloud Project with Firestore and Calendar APIs enabled
- MCP server URLs for Firestore and Calendar tools

### Local Development

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd drone_air_time
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   Create a `.env` file with:
   ```env
   MCP_FIRESTORE_URL=http://localhost:port
   MCP_CALENDAR_URL=http://localhost:port
   GOOGLE_CLOUD_PROJECT=your-project-id
   ```
   Note: MCP servers must be running locally for development.

5. **Run the application**:
   ```bash
   python main.py
   ```
   The API will be available at `http://localhost:8000`

### Testing

Use tools like `curl` or Postman to test the API:

```bash
curl -X POST "http://localhost:8000/v1/drone-air-time" \
     -H "Content-Type: application/json" \
     -d '{
       "location": {"latitude": 37.7749, "longitude": -122.4194},
       "date": "2024-01-15"
     }'
```

## Deployment

### Docker Deployment

1. **Build the Docker image**:
   ```bash
   docker build -t drone-flight-api .
   ```

2. **Run locally**:
   ```bash
   docker run -p 8000:8000 drone-flight-api
   ```

### Google Cloud Run Deployment

1. **Build and push to Google Container Registry**:
   ```bash
   gcloud builds submit --tag gcr.io/YOUR_PROJECT/drone-flight-api
   ```

2. **Deploy to Cloud Run**:
   ```bash
   gcloud run deploy drone-flight-api \
     --image gcr.io/YOUR_PROJECT/drone-flight-api \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars MCP_FIRESTORE_URL=YOUR_MCP_URL,MCP_CALENDAR_URL=YOUR_MCP_URL
   ```

## Configuration

### Environment Variables
- `MCP_FIRESTORE_URL`: URL for Firestore MCP server
- `MCP_CALENDAR_URL`: URL for Calendar MCP server
- `GOOGLE_CLOUD_PROJECT`: Google Cloud project ID

### MCP Servers
The API requires MCP servers for:
- **Firestore MCP**: Handles data persistence operations
- **Calendar MCP**: Manages calendar scheduling

Ensure these servers are configured and accessible.

## Dependencies

Key dependencies include:
- `fastapi`: Web framework
- `google-adk`: Agent development kit
- `httpx`: HTTP client for API calls
- `pydantic`: Data validation
- `uvicorn`: ASGI server

See `requirements.txt` for complete list.

## Error Handling

The API includes comprehensive error handling:
- MCP connection timeouts with retries
- JSON parsing fallbacks for agent responses
- Validation of input parameters
- Graceful degradation when services are unavailable

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
