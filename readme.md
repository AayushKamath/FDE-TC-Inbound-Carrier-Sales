## Introduction
------------
This project is part of a Technical Challenge. The use case in question is the implementation of an agent using the Happy Robot platform to automate inbound carrier calls. Carriers call in to request loads. The system must authenticate them, match them to viable loads, and negotiate pricing automatically.
As part of the solution, I simulate a call as a carrier and speak to the agent I configured on the Happy Robot platform.

## Features & Objectives
------------
1. MC number verification via FMCSA API
2. Load search from Data (json file)
3. Automated pitch and counter-offer negotiation (up to 3 rounds)
4. Call classification (outcome + sentiment)
5. Metrics dashboard/report
6. Secure API with API key authentication
7. Containerization with Docker
8. AWS Cloud deployment

## Features & Objectives
------------
1. Backend: Python, FastAPI
2. Frontend/Dashboard: Streamlit
3. Database: SQLite (local implementation) / Postgres RDS (AWS deployment)
4. Deployment: Docker + AWS (Platform + CLIv2) + Terraform
5. External APIs: FMCSA verification, HappyRobot web call trigger
6. Security: API Key Auth, HTTPS

## Dependencies and Installation (Local Implementation)
----------------------------

1. Clone the repository to your local machine.

2. Install the required dependencies by running the following command:
   ```
   pip install -r requirements.txt
   ```

3. An FMCSA key is required for carrier verification. Add it to the `.env` file in the project directory.
   Create an internal api key as well to pass through Webhooks from the Happy Robot platform everytime an API request is made to your local endpoint.
```commandline
FMCSA_API_KEY=fmcsa-api-key
INTERNAL_API_KEY =internal-api-key
```

4. For having a local endpoint that can be used for making API requests from the Happy Robot platform, use ngrok. Get a free Authtoken from ngrok after installing it in your system.
```
ngrok config add-authtoken YOUR_AUTHTOKEN
ngrok http 8000
```
This gives you an endpoint which you can set in the Webhooks as the url for all the necessary API requests from the Happy Robot Platform.

5. Backend + Dashboard
backend.main → backend is the folder, main is the python file name.
app → the FastAPI instance inside main.py.
--reload → auto-reloads on code changes (dev mode).
--host 0.0.0.0 → makes it accessible to external services like ngrok.
--port 8000 → matches the ngrok tunnel command (ngrok http 8000).
```
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
   For Streamlit
   app.py is in the folder named dashboard. This renders the UI for the dashboard which includes charts and metrics for the sales calls.
```
streamlit run dashboard/app.py
```

## Containerization with Docker
----------------------------
This project ships with Docker configs for both services:
Backend API (FastAPI / Uvicorn) — built from Dockerfile.backend and exposes 8000
Metrics Dashboard (e.g., Streamlit) — built from Dockerfile.dashboard and exposes 8501

Prerequisites:
- Docker Desktop installed and running (Windows/macOS) or Docker Engine (Linux)
- Optional: .env file at repo root for secrets & config (e.g., API keys, DB URL).
  The docker-compose.yml typically loads this automatically if present.

```bash
# Build images for all services
docker compose build

# Start containers in the background
docker compose up -d

# View logs (all services)
docker compose logs -f

# OR view logs per service
docker compose logs -f backend
docker compose logs -f dashboard

# Stop containers
docker compose down

```

Expected URLs

- Backend API: http://localhost:8000 (mapped from container port 8000)

- Dashboard: http://localhost:8501 (mapped from container port 8501)

