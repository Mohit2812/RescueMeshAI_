import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import requests

load_dotenv()

from incident_agent import analyze_incident
from verification_agent import verify_reports
from priority_agent import assess_priority
from resource_agent import allocate_resources
from route_medical_agent import get_route, find_nearby_hospitals

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rescuemesh")

app = FastAPI(
    title="RescueMesh AI API",
    description="Human-in-the-loop emergency response decision-support prototype",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://rescue-mesh-ai-195l.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MVP persistence only. Replace with PostgreSQL for multi-user/deployed use.
INCIDENTS: dict[str, dict[str, Any]] = {}
MISSIONS: dict[str, dict[str, Any]] = {}

SAFETY_NOTICE = (
    "RescueMesh AI is a prototype decision-support tool. All AI outputs "
    "are preliminary. A qualified human operator must verify the incident, "
    "route, facility suitability, resource availability, and approve any mission. "
    "No emergency services are contacted and no teams are dispatched."
)


class IncidentCreate(BaseModel):
    report: str = Field(min_length=3, max_length=5000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    reports: list[str] = Field(default_factory=list, max_length=10)


class MissionPlanRequest(BaseModel):
    report: str = Field(min_length=3, max_length=5000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    staging_latitude: float = Field(28.6315, ge=-90, le=90)
    staging_longitude: float = Field(77.2167, ge=-180, le=180)
    radius: int = Field(5000, ge=100, le=50000)
    reports: list[str] = Field(default_factory=list, max_length=10)


class MissionDecision(BaseModel):
    operator: str = Field(default="Demo operator", min_length=2, max_length=100)
    note: str = Field(default="", max_length=1000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_agents(report: str, reports: list[str], latitude: float,
                longitude: float, staging_latitude: float,
                staging_longitude: float, radius: int) -> dict[str, Any]:
    started = time.perf_counter()
    errors: list[dict[str, str]] = []

    # Incident extraction is core, but failures are surfaced rather than hidden.
    try:
        incident = analyze_incident(report)
    except Exception as exc:
        logger.exception("Incident agent failed")
        incident = {
            "incident_type": "unknown",
            "location": "unknown",
            "people_at_risk": "unknown",
            "medical_needs": [],
            "hazards": [],
            "access_status": "unknown",
            "urgency": "unknown",
            "uncertainties": ["AI extraction failed; manual review required."],
        }
        errors.append({"agent": "incident", "error": str(exc)})

    all_reports = [r.strip() for r in [report, *reports] if isinstance(r, str) and r.strip()]
    # Verification requires at least two reports; don't duplicate the same report
    # to manufacture corroboration.
    unique_reports = list(dict.fromkeys(all_reports))
    try:
        verification = verify_reports(unique_reports)
    except Exception as exc:
        logger.exception("Verification agent failed")
        verification = {
            "status": "verification_failed",
            "verified_facts": [],
            "conflicting_information": [],
            "unknown_information": ["Verification unavailable; manual verification required."],
            "confidence_score": 0,
            "human_verification_required": True,
        }
        errors.append({"agent": "verification", "error": str(exc)})

    try:
        priority = assess_priority(incident)
    except Exception as exc:
        logger.exception("Priority agent failed")
        priority = {
            "priority": "unknown",
            "severity": "unknown",
            "confidence": 0,
            "reasons": ["AI priority assessment unavailable."],
            "human_review_required": True,
        }
        errors.append({"agent": "priority", "error": str(exc)})

    try:
        resources = allocate_resources(incident, priority)
    except Exception as exc:
        logger.exception("Resource agent failed")
        resources = {
            "required_resources": [],
            "available_resources": [],
            "resource_gaps": [],
            "warnings": ["Resource recommendation unavailable; use manual allocation."],
            "human_approval_required": True,
        }
        errors.append({"agent": "resource", "error": str(exc)})

    route = get_route(
        {"latitude": staging_latitude, "longitude": staging_longitude},
        {"latitude": latitude, "longitude": longitude},
    )
    hospitals = find_nearby_hospitals(latitude, longitude, radius)

    return {
        "incident": incident,
        "verification": verification,
        "priority": priority,
        "resources": resources,
        "route": route,
        "nearby_hospitals": hospitals,
        "agent_errors": errors,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "human_review_required": True,
        "safety_notice": SAFETY_NOTICE,
    }


@app.get("/")
def home():
    return {"message": "RescueMesh AI API is running", "docs": "/docs", "health": "/api/health"}


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "RescueMesh AI", "timestamp": _now()}


@app.get("/api/incidents")
def list_incidents():
    return {"items": list(INCIDENTS.values()), "count": len(INCIDENTS)}


@app.post("/api/incidents")
def create_incident(payload: IncidentCreate):
    incident_id = str(uuid.uuid4())
    item = {
        "id": incident_id,
        "report": payload.report.strip(),
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "reports": payload.reports,
        "status": "NEW",
        "created_at": _now(),
        "analysis": None,
        "mission_id": None,
    }
    INCIDENTS[incident_id] = item
    return item


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str):
    item = INCIDENTS.get(incident_id)
    if not item:
        raise HTTPException(status_code=404, detail="Incident not found")
    return item


@app.post("/api/incidents/{incident_id}/analyze")
@app.post("/api/incidents/{incident_id}/agents")
def analyze_saved_incident(incident_id: str):
    item = INCIDENTS.get(incident_id)
    if not item:
        raise HTTPException(status_code=404, detail="Incident not found")

    result = _run_agents(
        report=item["report"],
        reports=item.get("reports", []),
        latitude=item["latitude"],
        longitude=item["longitude"],
        staging_latitude=28.6315,
        staging_longitude=77.2167,
        radius=5000,
    )
    item["analysis"] = result
    item["status"] = "ANALYZED"
    item["updated_at"] = _now()
    return result


@app.post("/api/incidents/{incident_id}/mission")
def create_mission(incident_id: str):
    item = INCIDENTS.get(incident_id)
    if not item:
        raise HTTPException(status_code=404, detail="Incident not found")
    if not item.get("analysis"):
        raise HTTPException(status_code=409, detail="Analyze the incident before generating a mission")

    analysis = item["analysis"]
    mission_id = str(uuid.uuid4())
    mission = {
        "id": mission_id,
        "incident_id": incident_id,
        "status": "PENDING_APPROVAL",
        "created_at": _now(),
        "updated_at": _now(),
        "closed_at": None,
        "history": [{
            "action": "REGISTERED",
            "by": "System",
            "note": "Mission registered and submitted for operator approval.",
            "timestamp": _now(),
        }],
        "priority": analysis.get("priority", {}),
        "incident": analysis.get("incident", {}),
        "resources": analysis.get("resources", {}),
        "route": analysis.get("route", {}),
        "nearby_hospitals": analysis.get("nearby_hospitals", {}),
        "verification": analysis.get("verification", {}),
        "human_approval_required": True,
        "approved_by": None,
        "decision_note": "",
        "safety_notice": SAFETY_NOTICE,
    }
    MISSIONS[mission_id] = mission
    item["mission_id"] = mission_id
    item["status"] = "MISSION_PENDING_APPROVAL"
    item["updated_at"] = _now()
    return mission


@app.get("/api/missions")
def list_missions():
    """List missions newest-first for Mission Control."""
    return {
        "missions": sorted(
            MISSIONS.values(),
            key=lambda mission: mission.get("created_at", ""),
            reverse=True,
        ),
        "count": len(MISSIONS),
    }


@app.get("/api/missions/{mission_id}")
def get_mission(mission_id: str):
    mission = MISSIONS.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@app.post("/api/missions/{mission_id}/approve")
def approve_mission(mission_id: str, decision: MissionDecision):
    mission = MISSIONS.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission["status"] != "PENDING_APPROVAL":
        raise HTTPException(status_code=409, detail="Only pending missions can be approved")
    mission["status"] = "ACTIVE"
    mission["approved_by"] = decision.operator
    mission["decision_note"] = decision.note
    mission["updated_at"] = _now()
    mission.setdefault("history", []).append({
        "action": "APPROVED",
        "by": decision.operator,
        "note": decision.note,
        "timestamp": mission["updated_at"],
    })
    return mission


@app.post("/api/missions/{mission_id}/reject")
def reject_mission(mission_id: str, decision: MissionDecision):
    mission = MISSIONS.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission["status"] != "PENDING_APPROVAL":
        raise HTTPException(status_code=409, detail="Only pending missions can be rejected")
    mission["status"] = "REJECTED"
    mission["approved_by"] = decision.operator
    mission["decision_note"] = decision.note
    mission["updated_at"] = _now()
    mission.setdefault("history", []).append({
        "action": "REJECTED",
        "by": decision.operator,
        "note": decision.note,
        "timestamp": mission["updated_at"],
    })
    return mission


@app.post("/api/missions/{mission_id}/close")
def close_mission(mission_id: str, decision: MissionDecision):
    mission = MISSIONS.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="Only active missions can be closed")
    mission["status"] = "CLOSED"
    mission["closed_at"] = _now()
    mission["updated_at"] = mission["closed_at"]
    mission["closed_by"] = decision.operator
    mission["decision_note"] = decision.note
    mission.setdefault("history", []).append({
        "action": "CLOSED",
        "by": decision.operator,
        "note": decision.note,
        "timestamp": mission["closed_at"],
    })
    return mission


# Compatibility endpoint used by earlier experiments / Swagger testing.
@app.post("/mission-plan")
def mission_plan(request: MissionPlanRequest):
    return _run_agents(
        report=request.report,
        reports=request.reports,
        latitude=request.latitude,
        longitude=request.longitude,
        staging_latitude=request.staging_latitude,
        staging_longitude=request.staging_longitude,
        radius=request.radius,
    )


# Location search and emergency contact discovery
class GeocodeRequest(BaseModel):
    address: str = Field(min_length=3, max_length=300)

class EmergencyContactsRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius: int = Field(default=10000, ge=500, le=50000)
    incident_type: str = Field(default="", max_length=300)

@app.post("/api/geocode")
def geocode_address(payload: GeocodeRequest):
    """Resolve operator-entered address or landmark to coordinates."""
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": payload.address, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": "RescueMeshAI/1.0 (hackathon prototype)"},
            timeout=12,
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            raise HTTPException(status_code=404, detail="No matching location found. Try a more specific address or landmark.")
        item = results[0]
        return {"display_name": item.get("display_name", payload.address),
                "latitude": float(item["lat"]), "longitude": float(item["lon"]),
                "source": "OpenStreetMap Nominatim", "human_confirmation_required": True}
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Location search unavailable: {exc}") from exc

@app.post("/api/emergency-contacts")
def emergency_contacts(payload: EmergencyContactsRequest):
    """Find mapped local police/fire contacts and return India-wide emergency numbers."""
    lat, lon, radius = payload.latitude, payload.longitude, payload.radius
    query = f"""
    [out:json][timeout:18];
    (
      nwr["amenity"="police"](around:{radius},{lat},{lon});
      nwr["emergency"="fire_service"](around:{radius},{lat},{lon});
      nwr["amenity"="fire_station"](around:{radius},{lat},{lon});
    );
    out center tags;
    """
    local, errors = [], []
    for endpoint in ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]:
        try:
            response = requests.post(endpoint, data={"data": query},
                headers={"User-Agent": "RescueMeshAI/1.0 (hackathon prototype)"}, timeout=(4, 22))
            response.raise_for_status()
            data = response.json()
            seen = set()
            for element in data.get("elements", []):
                tags = element.get("tags", {})
                if element.get("type") == "node":
                    elat, elon = element.get("lat"), element.get("lon")
                else:
                    center = element.get("center", {})
                    elat, elon = center.get("lat"), center.get("lon")
                if elat is None or elon is None:
                    continue
                if tags.get("amenity") == "police":
                    category = "Police"
                elif tags.get("amenity") == "fire_station" or tags.get("emergency") == "fire_service":
                    category = "Fire brigade"
                else:
                    continue
                key = (element.get("type"), element.get("id"))
                if key in seen:
                    continue
                seen.add(key)
                address = ", ".join(part for part in [
                    tags.get("addr:housenumber"), tags.get("addr:street"),
                    tags.get("addr:suburb"), tags.get("addr:city"), tags.get("addr:postcode")
                ] if part)
                local.append({
                    "id": f"osm-{key[0]}-{key[1]}", "category": category,
                    "name": tags.get("name") or f"Mapped {category.lower()} station",
                    "phone": tags.get("phone") or tags.get("contact:phone") or tags.get("telephone") or "",
                    "address": address or tags.get("addr:full") or "Address not listed in map data",
                    "latitude": float(elat), "longitude": float(elon), "source": "OpenStreetMap",
                    "contact_verified": False,
                    "note": "Map listing only; call to confirm the number and current availability."
                })
            break
        except (requests.RequestException, ValueError) as exc:
            errors.append(str(exc))
    national = [
        {"category":"All-emergency helpline","name":"Emergency Response Support System","phone":"112",
         "address":"India-wide emergency number","source":"Government emergency number","contact_verified":True,
         "note":"Call directly for emergency assistance; RescueMesh does not place calls."},
        {"category":"Fire brigade","name":"Fire emergency number","phone":"101","address":"India-wide helpline",
         "source":"India emergency helpline reference","contact_verified":True,"note":"Confirm local routing with the operator."},
        {"category":"Ambulance","name":"Ambulance emergency number","phone":"108",
         "address":"India-wide helpline (availability may vary by state)","source":"India emergency helpline reference",
         "contact_verified":True,"note":"Confirm local service coverage."}
    ]
    disaster_keywords = ("flood","earthquake","collapse","collapsed","building destruction",
                         "destruction","landslide","cyclone","major fire","mass casualty")
    ndrf_included = any(word in payload.incident_type.lower() for word in disaster_keywords)
    if ndrf_included:
        national.append({
            "category":"NDRF","name":"National Disaster Response Force (NDRF) control room",
            "phone":"+91-9711077372; HQ: 011-23438091 / 011-23438136","address":"NDRF Headquarters, New Delhi, India",
            "source":"NDRF contact reference; verify before relying","contact_verified":False,
            "note":"For major disasters. Contact official control room and local authorities; this is not a dispatch confirmation."
        })
    local.sort(key=lambda c: (c["category"], c["name"].lower()))
    return {"success":True,"nearby_contacts":local[:50],"national_contacts":national,
            "radius_meters":radius,"local_lookup_errors":errors,"ndrf_recommended":ndrf_included,
            "human_verification_required":True,
            "message":"Local station data comes from map listings and may omit phone/address details. Call to confirm."}
