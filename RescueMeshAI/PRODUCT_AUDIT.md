# Product audit & next steps

## What was present in the uploaded archive

- Python AI agent modules and a FastAPI backend existed.
- The archive did **not** contain a complete React application: the root `package.json` only listed map libraries and had no frontend scripts or app source.
- The previous backend offered `/mission-plan`, `/incident`, and `/route`, but did not implement the PRD's full incident-to-mission lifecycle endpoints.
- The verification agent correctly reports `insufficient_reports` when fewer than two distinct reports are supplied.
- Hospital lookup uses OpenStreetMap/Overpass and the India Hospital Directory ArcGIS endpoint. These are directory/map sources, not live hospital-capacity feeds.
- The routing module uses the public OSRM demo service. It does not check live closures or emergency vehicle restrictions.

## Included in this updated MVP

- React + Vite responsive command-center UI with map, incident intake, agent activity, evidence/uncertainty, mission review, and approval/rejection views.
- FastAPI endpoints for creating/listing incidents, analyzing, creating missions, reading missions, and recording approve/reject decisions.
- Existing AI agent modules retained; orchestration now catches agent failures and shows fallback/uncertainty instead of crashing the whole mission plan.
- Hospital discovery results retain source labels and unverified/availability flags.
- `.env.example` instead of distributing the uploaded `.env` file.
- Local setup instructions and explicit safety limits.

## Current MVP limits (not hidden)

1. Incident and mission records are held in process memory and disappear on restart; PostgreSQL is not implemented.
2. Authentication, role-based access control, audit log persistence, and production security are not implemented.
3. The default responder/staging coordinates are a demo value; operators should be able to set a real staging location before using route estimates.
4. OSRM returns estimates, not a validated emergency route. It does not confirm road closures or safe access.
5. Hospital records do not confirm that the facility is open, accepting casualties, has beds, has specialists, or has ambulances.
6. The public Overpass/OSRM/ArcGIS services can be rate-limited, unavailable, or return stale/incomplete data.
7. The current AI integration performs inference through Nebius Token Factory; it does not fine-tune or train a model.
8. The frontend build could not be verified in this environment because dependency installation timed out. Install dependencies locally with `npm install` and run `npm run build`.

## Suggested NVIDIA/Nemotron evaluation plan

- Create a small synthetic, reviewed dataset for incident extraction (incident type, location string, people at risk, medical needs, hazards, access status, uncertainty).
- Split it into development and held-out evaluation examples; avoid personal/sensitive real incident data.
- Establish a baseline using the current Nebius-hosted Nemotron model.
- Measure field-level extraction accuracy, JSON-validity rate, priority agreement with human labels, hallucination/unsupported-claim rate, p50/p95 latency, and failure rate.
- Compare prompt/schema changes first; fine-tune only if evaluation shows a specific repeatable gap.
- Investigate NVIDIA NeMo fine-tuning and the model's supported license/training workflow. Confirm access to suitable NVIDIA GPU compute and model weights. A hosted inference endpoint alone does not mean you can train that model.
- Version datasets, prompts, model identifiers, evaluation reports, and model outputs. Keep human approval mandatory after any model change.
