# RescueMesh AI update notes

## Changes in this package
- Location map now renders before analysis and updates its incident pin when the address is geocoded or coordinates are edited.
- Location changes clear stale analysis/route results so old facilities and route lines are not presented for the new location.
- Mission Control now lists all missions returned by the backend, with status, registration time, last-updated time, and a Details action.
- Missions record registration, approval, rejection, and closure events with timestamps, operator names, and notes.
- Active missions can be closed from Mission Control.
- AI agent output budgets were increased by 2,000 tokens each:
  - incident_agent.py: 800 -> 2800
  - verification_agent.py: 1600 -> 3600
  - priority_agent.py: 700 -> 2700
  - resource_agent.py: 1800 -> 3800

## Important limitations
- Mission storage is in-memory in `main.py`. Mission records disappear when the backend process restarts and are not shared across multiple server instances. Use a persistent database before production use.
- Higher output token limits do not increase provider quota and may increase latency/cost. The model/provider's maximum context and output limits still apply.
- Geocoding uses OpenStreetMap Nominatim and requires internet access.
- Route/hospital information is a prototype decision aid, not a confirmation of road safety, hospital capacity, or dispatch.
