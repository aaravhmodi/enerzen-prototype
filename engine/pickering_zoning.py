"""Parcel-level Pickering zoning context from the locally scraped store.

scripts/scrape_pickering_zoning.py fills the store on the home server; this
module only reads it. A lookup is organized by the steps of a municipal
zoning review: what the city's data can answer (property, zoning, Official
Plan, overlays, frameworks) and what the applicant still has to supply. It is
preliminary context and never a zoning determination.
"""
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path

import shapely
from shapely import STRtree
from shapely.geometry import Point, shape

DEFAULT_STORE = Path(__file__).parent.parent / 'data' / 'municipal' / 'pickering'

# Geometry is kept in local metres around Pickering (equirectangular; error is
# well under 1% across the city) so areas and distances read in m.
REF_LAT = 43.85
M_PER_DEG_LAT = 111_132.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(REF_LAT))
SCALE = (M_PER_DEG_LON, M_PER_DEG_LAT)

# Overlays that matter when they are near, not only underneath, the parcel.
NEARBY_M = {'rail': 300, 'floodplain': 120, 'natural_heritage': 120, 'easements': 30, 'heritage': 60,
            'provincial_plans': 0, 'servicing': 60, 'topography': 0}
OVERLAYS = ('floodplain', 'natural_heritage', 'heritage', 'easements', 'rail', 'provincial_plans')

# What each overlay usually adds to a complete application (O. Reg. 545/06 and
# the City's pre-consultation list decide; these are prompts for that meeting).
OVERLAY_STUDIES = {
    'floodplain': 'Conservation authority review and permit; floodplain / erosion hazard limits on the survey',
    'natural_heritage': 'Environmental impact study and natural heritage feature limits (staked if required)',
    'heritage': 'Heritage impact assessment; archaeological assessment if potential is flagged',
    'easements': 'Easement holder consent; registered easements shown on the survey / reference plan',
    'rail': 'Rail proximity: noise and vibration study, setback / berm and consultation with the railway',
    'provincial_plans': 'Conformity with the provincial plan that applies (Greenbelt, Oak Ridges Moraine, '
                        'Seaton / federal lands) before local zoning',
}


def store_dir() -> Path:
    return Path(os.environ.get('PICKERING_DATA_DIR', DEFAULT_STORE))


def _to_metres(lon, lat):
    return (lon * M_PER_DEG_LON, lat * M_PER_DEG_LAT)


def _norm(value) -> str:
    return re.sub(r'[^a-z0-9]', '', str(value).lower())


class Layer:
    def __init__(self, meta: dict, collection: dict):
        self.meta = meta
        self.features, geoms = [], []
        for feature in collection.get('features', []):
            if not feature.get('geometry'):
                self.features.append((feature['properties'], None))
                continue
            try:
                geom = shapely.transform(shape(feature['geometry']), lambda xy: xy * SCALE)
            except Exception:
                continue
            if not geom.is_valid:
                geom = geom.buffer(0)
            self.features.append((feature['properties'], geom))
            geoms.append(len(self.features) - 1)
        self._indexed = geoms
        self.tree = STRtree([self.features[i][1] for i in geoms]) if geoms else None

    def near(self, point, distance: float):
        """(attributes, geometry, distance m) for features within distance of point, nearest first."""
        if self.tree is None:
            return []
        hits = []
        for i in self.tree.query(point.buffer(max(distance, 0.01))):
            attrs, geom = self.features[self._indexed[int(i)]]
            d = geom.distance(point)
            if d <= distance:
                hits.append((attrs, geom, round(d, 1)))
        return sorted(hits, key=lambda h: h[2])


@lru_cache(maxsize=1)
def _load(store: str, stamp: str):
    root = Path(store)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    layers = []
    for meta in manifest['layers']:
        path = root / meta['file']
        if path.exists():
            layers.append(Layer(meta, json.loads(path.read_text(encoding='utf-8'))))
    return manifest, layers


def load_store():
    """(manifest, layers), or (None, []) before the first scrape. Reloads after a re-scrape."""
    root = store_dir()
    manifest = root / 'manifest.json'
    if not manifest.exists():
        return None, []
    return _load(str(root), str(manifest.stat().st_mtime_ns))


def status() -> dict:
    manifest, layers = load_store()
    if manifest is None:
        return {'status': 'not_scraped', 'store': str(store_dir()),
                'detail': 'Run scripts/scrape_pickering_zoning.py on the server to download the City data.'}
    by_category = {}
    for layer in layers:
        entry = by_category.setdefault(layer.meta['category'] or 'other', [])
        entry.append({'name': layer.meta['name'], 'features': len(layer.features), 'source_url': layer.meta['url']})
    return {'status': 'available', 'retrieved_at': manifest['retrieved_at'], 'layers': by_category,
            'documents': len(manifest['documents']), 'errors': manifest['errors'],
            'catalog_layers': manifest.get('catalog_layers')}


def _clean(attrs: dict) -> dict:
    return {k: v for k, v in attrs.items() if v not in (None, '', ' ')
            and not re.fullmatch(r'(objectid|fid|shape[._]?\w*|globalid|st_\w+)', k, re.I)}


def _pick(attrs: dict, *patterns) -> str | None:
    for pattern in patterns:
        for key, value in attrs.items():
            if value not in (None, '') and re.search(pattern, key, re.I):
                return str(value).strip()
    return None


def find_property(query: str):
    """A point inside the parcel matching an address, roll number or PIN, or None."""
    _, layers = load_store()
    wanted = _norm(query)
    if not wanted:
        return None
    for layer in layers:
        if layer.meta['category'] not in ('parcels', 'addresses'):
            continue
        for attrs, geom in layer.features:
            if geom is None:
                continue
            for key, value in attrs.items():
                if value is None or not re.search(r'addr|civic|street|roll|arn|pin|legal|plan|lot', key, re.I):
                    continue
                if _norm(value) == wanted or (re.search(r'addr|civic', key, re.I) and _norm(value).startswith(wanted)):
                    p = geom.representative_point()
                    return {'latitude': p.y / M_PER_DEG_LAT, 'longitude': p.x / M_PER_DEG_LON,
                            'matched': {'layer': layer.meta['name'], 'field': key, 'value': value}}
    return None


def _document_refs(manifest: dict, zone_codes: list[str], bylaw_numbers: list[str]) -> list[dict]:
    """Downloaded documents that name this parcel's by-law, and the pages that mention its zone."""
    root, refs = store_dir(), []
    for doc in manifest['documents']:
        label = f"{doc['title']} {doc['url']}"
        named = [n for n in bylaw_numbers if re.search(rf'(?<!\d){re.escape(n)}(?!\d)', label)]
        if not (named or re.search(r'zoning|by-?law', label, re.I)):
            continue
        ref = {'title': doc['title'], 'url': doc['url'], 'file': doc['file'], 'names_parcel_bylaw': named}
        if doc.get('text_file') and zone_codes:
            pages = json.loads((root / doc['text_file']).read_text(encoding='utf-8'))
            hits = {code: [i + 1 for i, text in enumerate(pages)
                           if re.search(rf'(?<![A-Za-z0-9-]){re.escape(code)}(?![A-Za-z0-9])', text)][:25]
                    for code in zone_codes}
            ref['zone_pages'] = {code: p for code, p in hits.items() if p}
        if named or ref.get('zone_pages'):
            refs.append(ref)
    return sorted(refs, key=lambda r: (not r['names_parcel_bylaw'], r['title']))


def lookup(latitude: float, longitude: float) -> dict:
    manifest, layers = load_store()
    if manifest is None:
        return {**status(), 'label': 'Pickering data not downloaded yet'}
    point = Point(_to_metres(longitude, latitude))

    def hits(category, distance=0.0):
        found = []
        for layer in layers:
            if layer.meta['category'] == category:
                for attrs, geom, d in layer.near(point, distance):
                    found.append({'layer': layer.meta['name'], 'source_url': layer.meta['url'],
                                  'distance_m': d, 'attributes': _clean(attrs), '_geom': geom})
        return found

    parcels = hits('parcels')
    parcel = parcels[0] if parcels else None
    # Overlays and zoning are tested against the parcel boundary when there is one.
    subject = parcel['_geom'] if parcel and parcel['_geom'].area > 0 else point

    def against(category, distance=0.0):
        found = []
        for layer in layers:
            if layer.meta['category'] != category or layer.tree is None:
                continue
            for i in layer.tree.query(subject.buffer(max(distance, 0.01))):
                attrs, geom = layer.features[layer._indexed[int(i)]]
                d = round(geom.distance(subject), 1)
                if d > distance:
                    continue
                share = None
                if subject.area > 0 and geom.area > 0:
                    share = round(100 * geom.intersection(subject).area / subject.area, 1)
                found.append({'layer': layer.meta['name'], 'source_url': layer.meta['url'], 'distance_m': d,
                              'parcel_share_pct': share, 'attributes': _clean(attrs)})
        return sorted(found, key=lambda h: (h['distance_m'], -(h['parcel_share_pct'] or 0)))

    zoning = against('zoning')
    official_plan = against('official_plan')
    overlays = {c: against(c, NEARBY_M[c]) for c in OVERLAYS}
    servicing = against('servicing', NEARBY_M['servicing'])
    topography = against('topography', 30)
    addresses = [h for h in hits('addresses', 40)][:3]
    neighbourhood = hits('neighbourhoods')

    zone_codes = sorted({z for h in zoning if (z := _pick(h['attributes'], r'^zone$', r'zone_?(code|cat|class)?$',
                                                          r'zon', r'symbol'))})
    bylaw_numbers = sorted({n for h in zoning for k, v in h['attributes'].items()
                            if re.search(r'law|amend|^bl|_bl', k, re.I)
                            for n in re.findall(r'\b\d{3,4}/\d{2,4}\b|\b\d{4}\b', str(v))})
    triggered = [c for c in OVERLAYS if overlays[c]]

    property_id = None
    if parcel:
        a = parcel['attributes']
        property_id = {
            'address': _pick(a, r'addr|civic') or (addresses and _pick(addresses[0]['attributes'], r'addr|civic')),
            'roll_number': _pick(a, r'roll|arn'), 'pin': _pick(a, r'\bpin\b|^pin'),
            'legal_description': _pick(a, r'legal|plan|lot|conc'),
            'area_m2': round(parcel['_geom'].area, 1), 'perimeter_m': round(parcel['_geom'].length, 1),
            'layer': parcel['layer'], 'source_url': parcel['source_url'], 'attributes': a,
        }
    elif addresses:
        property_id = {'address': _pick(addresses[0]['attributes'], r'addr|civic'), 'attributes':
                       addresses[0]['attributes'], 'layer': addresses[0]['layer'],
                       'note': 'No parcel polygon matched; nearest address point only.'}

    return {
        'status': 'available' if parcel or zoning else 'not_found',
        'label': 'Preliminary Pickering parcel context' if parcel or zoning else 'Outside the downloaded City data',
        'detail': 'From the City of Pickering data stored on this server. Confirm with the City before relying '
                  'on any use, height, setback or parking rule; this is not a zoning determination.',
        'retrieved_at': manifest['retrieved_at'],
        'query': {'latitude': latitude, 'longitude': longitude},
        'steps': {
            '1_property_identification': {
                'from_city_data': property_id,
                'applicant_must_confirm': ['Municipal address or legal description (lot, concession, plan)',
                                           'PIN / roll number', 'Survey of the subject land boundaries'],
            },
            '2_existing_zoning_and_official_plan': {
                'zoning': zoning, 'zone_codes': zone_codes, 'bylaw_numbers': bylaw_numbers,
                'official_plan': official_plan, 'overlays': overlays,
                'neighbourhood': [h['attributes'] for h in neighbourhood][:1],
                'applicant_must_supply': ['Current use of the land', 'Existing structures and their uses'],
            },
            '3_proposed_development': {
                'applicant_must_supply': ['Proposed land use', 'Number and type of units',
                                          'Building size, height, footprint and density',
                                          'Lot layout: setbacks, parking, access/driveways, landscaped and '
                                          'loading areas'],
                'check_against': 'The zone standards on the by-law pages listed under step 6.',
            },
            '4_site_characteristics': {
                'servicing_nearby': servicing, 'topography': topography,
                'natural_heritage': overlays['natural_heritage'],
                'applicant_must_supply': ['Topographic survey (grades, slopes)', 'Servicing confirmation',
                                          'Adjacent land uses'],
            },
            '5_supporting_documents': {
                'always': ['Planning justification report', 'Concept site plan', 'Survey or reference plan'],
                'triggered_by_overlays': {c: OVERLAY_STUDIES[c] for c in triggered},
                'by_scale': ['Traffic impact study (larger developments)',
                             'Functional servicing report', 'Archaeological assessment (if required)'],
                'reference': 'O. Reg. 545/06 (complete application) and the City pre-consultation checklist',
            },
            '6_planning_frameworks': {
                'zoning_bylaw_references': _document_refs(manifest, zone_codes, bylaw_numbers),
                'official_plan_designation': [_pick(h['attributes'], r'desig', r'land_?use', r'name')
                                              for h in official_plan],
                'provincial': ['Provincial Planning Statement (2024)'] +
                              [h['layer'] for h in overlays['provincial_plans']],
            },
        },
    }
