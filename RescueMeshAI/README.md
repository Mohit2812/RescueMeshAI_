# RescueMesh AI — Hackathon MVP

**From scattered emergency signals to coordinated rescue missions.**

RescueMesh AI is a human-in-the-loop emergency decision-support prototype. It uses specialized AI agents to extract incident details, compare reports, assess preliminary priority, recommend resources, estimate routes, and find hospital directory records.

> **Safety boundary:** This is not a real dispatch system. AI outputs and directory entries are unverified. Route estimates do not include confirmed road closures or road safety. Hospital operating status, emergency department capability, beds, and ambulance availability are not confirmed. An authorized human operator must independently verify information and approve any simulated mission state.

## Project layout

```text
RescueMeshAI/
├── main.py
├── incident_agent.py
├── verification_agent.py
├── priority_agent.py
├── resource_agent.py
├── route_medical_agent.py
├── requirements.txt
├── .env.example
└── frontend/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.jsx
        └── styles.css
```

## Requirements

- Python 3.10+
- Node.js 18+ (Node 20+ recommended)
- A Nebius Token Factory API key for the Nemotron-powered agents
- Internet access for public routing/hospital data sources

## 1. Configure the backend

Open PowerShell in this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set your own `NEBIUS_API_KEY`. Never paste the key into source code, frontend environment variables, screenshots, or public repositories.

Start FastAPI:

```powershell
uvicorn main:app --reload
```

`main.py` loads `.env` for local development. API docs: http://127.0.0.1:8000/docs  
Health check: http://127.0.0.1:8000/api/health

## 2. Start the React frontend

Open a second PowerShell terminal in the project folder:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The frontend defaults to `https://rescuemeshai-mdlk.onrender.com`. To change it, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_BASE_URL`.

## 3. End-to-end demo

1. Check that the backend badge says **API connected**.
2. Click **Load demo scenario**, or enter an incident report and coordinates.
3. Add separate witness reports in the additional-reports field to let the Verification Agent compare claims. Repeated or copied reports are not independent proof.
4. Click **Analyze incident**. The backend runs incident extraction, verification, triage, resource recommendations, route estimates, and nearby hospital discovery.
5. Inspect the agent activity, evidence/unknowns, route, and hospital source labels.
6. Click **Generate mission for review**.
7. Add an operator name and note; approve or reject the simulated mission. This does not contact emergency services or dispatch a team.

## API endpoints

- `GET /api/health`
- `POST /api/incidents`
- `GET /api/incidents`
- `GET /api/incidents/{incident_id}`
- `POST /api/incidents/{incident_id}/analyze`
- `POST /api/incidents/{incident_id}/agents`
- `POST /api/incidents/{incident_id}/mission`
- `GET /api/missions/{mission_id}`
- `POST /api/missions/{mission_id}/approve`
- `POST /api/missions/{mission_id}/reject`
- `POST /mission-plan` (compatibility endpoint)

The current MVP stores incidents and missions in process memory; restarting the backend clears them. Add PostgreSQL and authentication before multi-user or deployed use.

## Agent review and known limitations

- **Incident Agent:** Nemotron extracts a structured preliminary incident record from the report. Its output is not independently verified.
- **Verification Agent:** compares distinct reports; a single report correctly returns `insufficient_reports`.
- **Priority Agent:** produces a preliminary priority and confidence. A human must review it.
- **Resource Agent:** estimates required resources against a demo inventory; it does not query real-time availability or dispatch.
- **Route Agent:** OSRM provides road-route estimates. Public demo service limits apply, and live closures/safety are not checked.
- **Hospital discovery:** tries OpenStreetMap/Overpass and then the India Hospital Directory ArcGIS layer. Results are source-labeled and `verified: false`; availability is never inferred from a directory record. Public services can time out or change.
- **Mission workflow:** approve/reject endpoints update a simulated state only. They do not execute real-world actions.

## Before presenting to judges

- Test with multiple incident scenarios and missing/contradictory reports.
- Keep API keys out of the frontend and repository.
- Explain that the project is a prototype and not a substitute for emergency command authorities.
- Show source, uncertainty, agent failures, and the human approval gate.
- Record latency and agent failures. Do not claim model training or fine-tuning unless you actually perform and evaluate it.

## NVIDIA/Nemotron roadmap

This version uses a Nemotron model through Nebius Token Factory inference. That is **model inference, not training**. A credible next step is to create a small, reviewed dataset of synthetic/anonymized incident reports with ground-truth structured labels; evaluate extraction, priority consistency, hallucination rate, latency, and JSON validity; then investigate NVIDIA NeMo fine-tuning or another supported NVIDIA training workflow if hackathon infrastructure permits. Do not train on sensitive real incident data without authorization and privacy controls.


## Recent update: location dashboard and emergency contacts

- Added address/landmark search (`POST /api/geocode`) using OpenStreetMap Nominatim. Confirm the returned coordinates before analyzing.
- Added nearby police and fire-station discovery (`POST /api/emergency-contacts`) using OpenStreetMap/Overpass, including any phone and address tags present in the map data.
- Added India emergency helplines and conditionally includes NDRF contact details for incident descriptions containing terms such as flood, earthquake, collapse, landslide, cyclone, destruction, or mass casualty.
- The frontend now has an **Emergency Contacts** button after incident analysis, and hospital rows display the available phone number and address without an “Unverified” badge.
- Local contact details are sourced from map listings and can be missing or outdated. Verify by calling the official service. The app does not place calls or dispatch responders. NDRF contact details should be checked against official sources before operational use.
- The existing incident, verification, priority, resource, routing, hospital and human-approval workflow has been preserved.
