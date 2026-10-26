
"""
route_medical_agent.py
RescueMesh AI — Route and Hospital Discovery Agent

Routing: OSRM public demo service
Primary hospital source: OpenStreetMap / Overpass
Fallback hospital source: India Hospital Directory (ArcGIS)

IMPORTANT:
- Route estimates do not verify road safety or road closures.
- Hospital directory entries are not confirmation of current operation.
- This module never invents real hospital records.
"""

import math
import requests


# ---------------------------------------------------------
# API CONFIGURATION
# ---------------------------------------------------------

OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

INDIA_HOSPITAL_API = (
    "https://livingatlas.esri.in/server/rest/services/"
    "LivingAtlas/IND_Hospital_Directory/MapServer/0/query"
)

REQUEST_HEADERS = {
    "User-Agent": "RescueMeshAI/1.0 (hackathon emergency-response prototype)"
}

SAFETY_NOTICE = (
    "Prototype only. Route estimates do not confirm road safety, "
    "live closures, or emergency access. Hospital directory records "
    "do not confirm current operations, beds, or emergency capacity. "
    "Emergency personnel must verify all information."
)


# ---------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------

def _validate_coordinates(latitude, longitude):
    """Validate WGS84 latitude and longitude."""

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        raise ValueError("Latitude and longitude must be numbers.")

    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("Coordinates must be finite numbers.")

    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90.")

    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180.")

    return latitude, longitude


def _haversine_km(lat1, lon1, lat2, lon2):
    """Calculate straight-line distance in kilometers."""

    earth_radius_km = 6371.0

    lat1, lon1, lat2, lon2 = map(
        math.radians, [lat1, lon1, lat2, lon2]
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    a = min(1.0, max(0.0, a))

    return 2 * earth_radius_km * math.atan2(
        math.sqrt(a), math.sqrt(1 - a)
    )


# ---------------------------------------------------------
# ROUTE LOOKUP — OSRM
# ---------------------------------------------------------

def get_route(start, end):
    """
    Get driving-route alternatives from OSRM.

    start and end can be:
        (latitude, longitude)
        [latitude, longitude]
        {"latitude": ..., "longitude": ...}
        {"lat": ..., "lon": ...}

    Coordinates returned by OSRM geometry use [longitude, latitude].
    """

    def unpack_coordinates(value, label):
        if isinstance(value, dict):
            lat = value.get("latitude", value.get("lat"))
            lon = value.get(
                "longitude",
                value.get("lon", value.get("lng"))
            )
        elif isinstance(value, (tuple, list)) and len(value) >= 2:
            lat, lon = value[0], value[1]
        else:
            raise ValueError(
                f"{label} must be a coordinate pair or dictionary."
            )

        return _validate_coordinates(lat, lon)

    try:
        start_lat, start_lon = unpack_coordinates(start, "start")
        end_lat, end_lon = unpack_coordinates(end, "end")
    except ValueError as exc:
        return {
            "success": False,
            "routes": [],
            "message": str(exc),
            "safety_notice": SAFETY_NOTICE,
            "human_review_required": True,
        }

    # OSRM expects longitude,latitude.
    url = (
        f"{OSRM_URL}/"
        f"{start_lon},{start_lat};{end_lon},{end_lat}"
    )

    params = {
        "alternatives": "true",
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=(4, 20),
        )
        response.raise_for_status()
        data = response.json()

        if data.get("code") != "Ok":
            return {
                "success": False,
                "routes": [],
                "message": data.get(
                    "message", "Routing service returned an error."
                ),
                "safety_notice": SAFETY_NOTICE,
                "live_road_closures_checked": False,
                "human_review_required": True,
            }

        routes = []

        for index, route in enumerate(data.get("routes", []), start=1):
            steps = []

            for leg in route.get("legs", []):
                for step in leg.get("steps", []):
                    maneuver = step.get("maneuver", {})
                    steps.append({
                        "instruction": maneuver.get(
                            "instruction",
                            maneuver.get("type", "Continue")
                        ),
                        "distance_m": round(
                            step.get("distance", 0), 1
                        ),
                        "duration_seconds": round(
                            step.get("duration", 0), 1
                        ),
                        "road_name": step.get("name", ""),
                        "maneuver_type": maneuver.get("type", ""),
                    })

            routes.append({
                "route_id": index,
                "distance_km": round(
                    route.get("distance", 0) / 1000, 2
                ),
                "duration_minutes": round(
                    route.get("duration", 0) / 60, 1
                ),
                "geometry": route.get("geometry"),
                "instructions": steps,
                "source": "OSRM",
                "live_road_closures_checked": False,
            })

        return {
            "success": bool(routes),
            "routes": routes,
            "count": len(routes),
            "message": (
                "Route estimates retrieved. Verify road conditions "
                "with emergency personnel before dispatch."
                if routes
                else "No routes were returned by the routing service."
            ),
            "safety_notice": SAFETY_NOTICE,
            "live_road_closures_checked": False,
            "human_review_required": True,
        }

    except (requests.RequestException, ValueError) as exc:
        return {
            "success": False,
            "routes": [],
            "message": f"Routing service unavailable: {exc}",
            "safety_notice": SAFETY_NOTICE,
            "live_road_closures_checked": False,
            "human_review_required": True,
        }


# ---------------------------------------------------------
# SOURCE 1 — OPENSTREETMAP / OVERPASS
# ---------------------------------------------------------

def _find_osm_hospitals(latitude, longitude, radius):
    """Return nearby mapped hospitals from Overpass."""

    query = f"""
    [out:json][timeout:15];
    nwr["amenity"="hospital"]
       (around:{radius},{latitude},{longitude});
    out center tags;
    """

    errors = []

    for endpoint in OVERPASS_URLS:
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers=REQUEST_HEADERS,
                timeout=(4, 18),
            )
            response.raise_for_status()
            data = response.json()

            if "elements" not in data:
                raise ValueError(
                    "Overpass response did not contain elements."
                )

            hospitals = []

            for element in data["elements"]:
                tags = element.get("tags", {})

                # Nodes have lat/lon directly; ways and relations
                # commonly provide a representative center.
                if element.get("type") == "node":
                    lat = element.get("lat")
                    lon = element.get("lon")
                else:
                    center = element.get("center", {})
                    lat = center.get("lat")
                    lon = center.get("lon")

                if lat is None or lon is None:
                    continue

                lat, lon = _validate_coordinates(lat, lon)

                distance_km = _haversine_km(
                    latitude, longitude, lat, lon
                )

                if distance_km * 1000 > radius:
                    continue

                hospitals.append({
                    "id": (
                        f"osm-{element.get('type')}-"
                        f"{element.get('id')}"
                    ),
                    "name": tags.get("name", "Unnamed mapped hospital"),
                    "address": ", ".join(
                        part for part in [
                            tags.get("addr:street"),
                            tags.get("addr:city"),
                            tags.get("addr:postcode"),
                        ] if part
                    ),
                    "latitude": lat,
                    "longitude": lon,
                    "distance_km": round(distance_km, 2),
                    "phone": tags.get("phone"),
                    "facility_type": tags.get(
                        "healthcare", tags.get("amenity", "hospital")
                    ),
                    "source": "OpenStreetMap",
                    "source_id": (
                        f"{element.get('type')}/{element.get('id')}"
                    ),
                    "demo_data": False,
                    "verified": False,
                    "availability_confirmed": False,
                })

            # A successful query can legitimately return zero records.
            return {
                "success": True,
                "source": "OpenStreetMap",
                "count": len(hospitals),
                "hospitals": hospitals,
                "message": (
                    "Mapped hospital locations retrieved."
                    if hospitals
                    else "No mapped hospitals found within this radius."
                ),
            }

        except (
            requests.RequestException,
            ValueError,
            TypeError,
        ) as exc:
            errors.append(f"{endpoint}: {exc}")

    return {
        "success": False,
        "source": "OpenStreetMap",
        "count": 0,
        "hospitals": [],
        "message": "All Overpass endpoints failed. " + " | ".join(errors),
    }


# ---------------------------------------------------------
# SOURCE 2 — INDIA HOSPITAL DIRECTORY (ARCGIS)
# ---------------------------------------------------------

def find_government_directory_hospitals(
    latitude, longitude, radius=5000
):
    """
    Search the India Hospital Directory ArcGIS layer.

    Directory entries are not verified live facilities.
    Coordinates and distance are checked before returning records.
    """

    try:
        latitude, longitude = _validate_coordinates(
            latitude, longitude
        )

        radius = float(radius)
        if not math.isfinite(radius) or radius <= 0:
            raise ValueError("Radius must be a positive number.")

        params = {
            "where": "1=1",
            "outFields": (
                "objectid,health_facility_name,address,street,"
                "landmark,locality,posatalcode,landline_number,"
                "facility_type,state_name,district_name,"
                "taluka_name,block_name,lat,lon"
            ),
            "returnGeometry": "true",
            "geometry": (
                '{"x":'
                + str(longitude)
                + ',"y":'
                + str(latitude)
                + ',"spatialReference":{"wkid":4326}}'
            ),
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": radius,
            "units": "esriSRUnit_Meter",
            "outSR": "4326",
            "resultRecordCount": 2000,
            "f": "json",
        }

        response = requests.get(
            INDIA_HOSPITAL_API,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=(4, 20),
        )
        response.raise_for_status()
        data = response.json()

        if data.get("error"):
            raise RuntimeError(str(data["error"]))

        hospitals = []

        for feature in data.get("features", []):
            attributes = feature.get("attributes", {})
            geometry = feature.get("geometry") or {}

            lat = attributes.get("lat")
            lon = attributes.get("lon")

            # Fall back to the returned geometry if coordinate
            # attribute fields are absent.
            if lat is None:
                lat = geometry.get("y")
            if lon is None:
                lon = geometry.get("x")

            if lat is None or lon is None:
                continue

            try:
                lat, lon = _validate_coordinates(lat, lon)
            except ValueError:
                continue

            distance_km = _haversine_km(
                latitude, longitude, lat, lon
            )

            if distance_km * 1000 > radius:
                continue

            address_parts = [
                attributes.get("address"),
                attributes.get("locality"),
                attributes.get("district_name"),
                attributes.get("state_name"),
                attributes.get("posatalcode"),
            ]
            address = ", ".join(
                str(part).strip()
                for part in address_parts
                if part is not None and str(part).strip()
            )

            hospitals.append({
                "id": f"india-directory-{attributes.get('objectid')}",
                "name": (
                    attributes.get("health_facility_name")
                    or "Unnamed directory facility"
                ),
                "address": address,
                "latitude": lat,
                "longitude": lon,
                "distance_km": round(distance_km, 2),
                "phone": attributes.get("landline_number"),
                "facility_type": attributes.get("facility_type"),
                "state": attributes.get("state_name"),
                "district": attributes.get("district_name"),
                "source": "India Hospital Directory via ArcGIS",
                "demo_data": False,
                "verified": False,
                "availability_confirmed": False,
            })

        hospitals.sort(key=lambda item: item["distance_km"])

        return {
            "success": True,
            "source": "India Hospital Directory via ArcGIS",
            "count": len(hospitals),
            "hospitals": hospitals,
            "message": (
                "Directory records retrieved; operating status "
                "and emergency capacity are not confirmed."
                if hospitals
                else (
                    "The directory query succeeded, but no facilities "
                    "with usable coordinates were found within the radius."
                )
            ),
            "human_review_required": True,
        }

    except (
        requests.RequestException,
        ValueError,
        TypeError,
        RuntimeError,
    ) as exc:
        return {
            "success": False,
            "source": "India Hospital Directory via ArcGIS",
            "count": 0,
            "hospitals": [],
            "message": f"India hospital directory API failed: {exc}",
            "human_review_required": True,
        }


# ---------------------------------------------------------
# PUBLIC FUNCTION — NEARBY HOSPITALS
# ---------------------------------------------------------

def find_nearby_hospitals(latitude, longitude, radius=5000):
    """
    Find nearby hospital records.

    Order:
      1. OpenStreetMap / Overpass
      2. India Hospital Directory / ArcGIS

    The government directory is also tried if OSM returns zero
    records, not just when the OSM request times out.

    No fictional hospitals are returned.
    """

    try:
        latitude, longitude = _validate_coordinates(
            latitude, longitude
        )

        radius = float(radius)

        if not math.isfinite(radius) or radius <= 0:
            raise ValueError("Radius must be a positive number.")

    except ValueError as exc:
        return {
            "success": False,
            "count": 0,
            "hospitals": [],
            "source": None,
            "message": str(exc),
            "human_review_required": True,
        }

    osm_result = _find_osm_hospitals(
        latitude, longitude, radius
    )

    # Use OSM records when the query succeeds and finds hospitals.
    if osm_result["success"] and osm_result["hospitals"]:
        hospitals = osm_result["hospitals"]
        hospitals.sort(key=lambda item: item["distance_km"])

        return {
            "success": True,
            "count": len(hospitals),
            "hospitals": hospitals,
            "source": "OpenStreetMap",
            "live_lookup_success": True,
            "demo_fallback_used": False,
            "message": (
                "Nearby mapped hospitals found. Their operational "
                "status and emergency capacity are not confirmed."
            ),
            "safety_notice": SAFETY_NOTICE,
            "human_review_required": True,
        }

    # OSM failed or found no records: try the government directory.
    government_result = find_government_directory_hospitals(
        latitude, longitude, radius
    )

    if government_result["success"] and government_result["hospitals"]:
        hospitals = government_result["hospitals"]

        return {
            "success": True,
            "count": len(hospitals),
            "hospitals": hospitals,
            "source": "India Hospital Directory via ArcGIS",
            "live_lookup_success": False,
            "directory_fallback_used": True,
            "demo_fallback_used": False,
            "message": (
                "Showing government-directory records because "
                "OpenStreetMap returned no usable hospital results. "
                "These records are not live confirmation of hospital "
                "operations, beds, or emergency capacity."
            ),
            "osm_message": osm_result["message"],
            "safety_notice": SAFETY_NOTICE,
            "human_review_required": True,
        }

    # Both sources failed or found no usable records.
    no_records = (
        osm_result["success"]
        and government_result["success"]
    )

    return {
        "success": False,
        "count": 0,
        "hospitals": [],
        "source": None,
        "live_lookup_success": False,
        "directory_fallback_used": False,
        "demo_fallback_used": False,
        "message": (
            "Both sources responded, but no usable nearby hospital "
            "records were found."
            if no_records
            else (
                "No hospital records could be retrieved. "
                "One or more data sources may be unavailable."
            )
        ),
        "osm_message": osm_result["message"],
        "government_directory_message": government_result["message"],
        "safety_notice": SAFETY_NOTICE,
        "human_review_required": True,
    }
