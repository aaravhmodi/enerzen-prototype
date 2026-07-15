"""
One-off generator: read the NBCC snow-load workbook and write
data/ontario_locations.json (committed; the xlsx is not a runtime dependency).

    python scripts/build_locations.py "<path to xlsx>"

Each location gets:
  ss, sr            ground snow load + associated rain load, kPa (from workbook)
  climate_zone      6 / 7a / 7b  (auto-classified; user-overridable in the app)
  region            utility/geographic region key -> data/assemblies.json regions
Only Ontario is extracted for now.
"""

import json
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).parent.parent
OUT = ROOT / "data" / "ontario_locations.json"

# ── Climate-zone classification ──────────────────────────────────────────────
# Per-town HDD is not in the workbook, so zones are assigned by known city.
# Substring match, first hit wins; everything unmatched defaults to 7a.
ZONE_SOUTH_6 = [
    "Toronto", "Mississauga", "Brampton", "Oakville", "Burlington", "Milton",
    "Markham", "Vaughan", "Richmond Hill", "Aurora", "Newmarket", "Pickering",
    "Ajax", "Whitby", "Oshawa", "Hamilton", "Windsor", "London", "Kitchener",
    "Waterloo", "Cambridge", "Guelph", "Brantford", "Sarnia", "Chatham",
    "Woodstock", "Stratford", "St. Catharines", "St Catharines", "Niagara",
    "Welland", "Fort Erie", "Port Colborne", "Leamington", "Tillsonburg",
    "St. Thomas", "St Thomas", "Ingersoll", "Simcoe", "Dunnville", "Hagersville",
    "Ailsa Craig", "Wallaceburg", "Strathroy", "Aylmer", "Dresden",
]
ZONE_NORTH_7B = [
    "Sudbury", "Thunder Bay", "Timmins", "Sault Ste", "North Bay", "Kapuskasing",
    "Kenora", "Dryden", "Cochrane", "Hearst", "Kirkland Lake", "Wawa", "Chapleau",
    "Hornepayne", "Marathon", "Nipigon", "Schreiber", "Fort Frances",
    "Sioux Lookout", "Red Lake", "Elliot Lake", "Espanola", "New Liskeard",
    "Earlton", "Iroquois Falls", "Moosonee", "Big Trout Lake", "Atikokan",
    "Geraldton", "Manitouwadge", "Terrace Bay", "White River", "Armstrong",
    "Pickle Lake", "Sturgeon Falls", "Blind River", "Gore Bay", "Little Current",
    "Cochrane", "Smooth Rock", "Longlac", "Beardmore",
]


def classify_zone(name: str) -> str:
    for kw in ZONE_NORTH_7B:
        if name.startswith(kw):
            return "7b"
    for kw in ZONE_SOUTH_6:
        if name.startswith(kw):
            return "6"
    return "7a"


def classify_region(name: str, zone: str) -> str:
    """Utility/geographic region for regional rates + soil defaults."""
    if name.startswith("Toronto"):
        return "toronto"
    if zone == "7b":
        return "northern"
    if zone == "6":
        return "southern"
    return "eastern"


PROVINCES = {
    "British Columbia", "Alberta", "Saskatchewan", "Manitoba", "Ontario",
    "Quebec", "New Brunswick", "Nova Scotia", "Prince Edward Island",
    "Newfoundland and Labrador", "Yukon", "Northwest Territories", "Nunavut",
}


def main() -> int:
    if len(sys.argv) < 2:
        print('usage: python scripts/build_locations.py "<path to xlsx>"', file=sys.stderr)
        return 1

    wb = openpyxl.load_workbook(sys.argv[1], data_only=True, read_only=True)
    ws = wb["Climatic Data 2015"]

    current = None
    locations = {}
    for row in ws.iter_rows(min_row=1, values_only=True):
        a, b, c = row[0], row[1], row[2]
        if a and isinstance(a, str):
            name = a.strip()
            if name in PROVINCES or any(name.startswith(p) for p in PROVINCES):
                current = name
                continue
            if current and current.startswith("Ontario") and b is not None:
                try:
                    ss, sr = float(b), float(c if c is not None else 0.4)
                except (TypeError, ValueError):
                    continue
                zone = classify_zone(name)
                locations[name] = {
                    "ss": ss,
                    "sr": sr,
                    "climate_zone": zone,
                    "region": classify_region(name, zone),
                }

    payload = {
        "_source": "NBCC 2015 Climatic Data (Snow Load Calculation workbook v1.3), "
                   "Ontario only. ss/sr from workbook; climate_zone and region "
                   "auto-classified and user-overridable.",
        "locations": dict(sorted(locations.items())),
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    from collections import Counter
    zc = Counter(v["climate_zone"] for v in locations.values())
    rc = Counter(v["region"] for v in locations.values())
    print(f"wrote {OUT.relative_to(ROOT)} — {len(locations)} Ontario locations")
    print(f"  zones:   {dict(zc)}")
    print(f"  regions: {dict(rc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
