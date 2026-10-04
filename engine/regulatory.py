"""Small, read-only connectors for parcel-level planning intelligence."""

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TORONTO_ZONING_SOURCE_URL = "https://open.toronto.ca/dataset/zoning-by-law/"
TORONTO_ZONING_QUERY_URL = (
    "https://gis.toronto.ca/arcgis/rest/services/cot_geospatial11/MapServer/18/query"
)


def toronto_zoning_lookup(latitude: float, longitude: float) -> dict:
    """Look up the Toronto zoning summary polygon intersecting a point.

    This is a preliminary planning lookup, not a permit or zoning opinion. The
    municipal service can be unavailable, so callers receive a safe status.
    """
    params = urlencode(
        {
            "where": "1=1",
            "geometry": f"{longitude},{latitude}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "ADDRESS_F,ZN_STRING,HT_STRING,PA_STRING,RMH_STRING,COV_STRING,CNV_STRING",
            "returnGeometry": "false",
            "f": "json",
        }
    )
    request = Request(
        f"{TORONTO_ZONING_QUERY_URL}?{params}",
        headers={"User-Agent": "EnerZen/0.1 municipal planning lookup"},
    )

    try:
        with urlopen(request, timeout=8) as response:
            payload = json.load(response)
    except Exception as exc:  # network/service failures must not block modeling
        return {
            "status": "unavailable",
            "label": "Municipal service unavailable",
            "detail": "Toronto zoning could not be checked right now; continue only with professional planning review.",
            "error_type": type(exc).__name__,
            "source_url": TORONTO_ZONING_SOURCE_URL,
            "source_label": "City of Toronto Zoning By-law dataset",
        }

    if payload.get("error"):
        return {
            "status": "unavailable",
            "label": "Municipal service returned an error",
            "detail": "Toronto zoning could not be checked right now; continue only with professional planning review.",
            "source_url": TORONTO_ZONING_SOURCE_URL,
            "source_label": "City of Toronto Zoning By-law dataset",
        }

    features = payload.get("features", [])
    if not features:
        return {
            "status": "not_found",
            "label": "No parcel match",
            "detail": "No Toronto zoning summary polygon intersected this point. Confirm the coordinates and parcel boundary.",
            "source_url": TORONTO_ZONING_SOURCE_URL,
            "source_label": "City of Toronto Zoning By-law dataset",
        }

    attributes = features[0].get("attributes", {})
    return {
        "status": "available",
        "label": "Preliminary parcel match",
        "detail": "Use these municipal attributes as planning context only; they do not replace a zoning review.",
        "parcel": {
            "address": attributes.get("ADDRESS_F"),
            "zoning": attributes.get("ZN_STRING"),
            "height": attributes.get("HT_STRING"),
            "policy_area": attributes.get("PA_STRING"),
            "rooming_house": attributes.get("RMH_STRING"),
            "lot_coverage": attributes.get("COV_STRING"),
            "conversion": attributes.get("CNV_STRING"),
        },
        "source_url": TORONTO_ZONING_SOURCE_URL,
        "source_label": "City of Toronto Zoning By-law dataset",
    }
