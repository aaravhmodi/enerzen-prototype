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
from shapely.geometry import Point, mapping, shape

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


def _to_wgs84(geom):
    return shapely.transform(geom, lambda xy: xy / SCALE)


def _label(attrs: dict) -> str | None:
    return _pick(attrs, r'full_?addr', r'addr', r'civic', r'legal', r'roll|arn', r'\bpin\b|^pin')


def search_properties(query: str, limit: int = 8) -> list[dict]:
    """Parcels and address points matching an address, roll number, PIN or legal description, best first.

    Exact matches rank before prefix matches, which rank before matches that only
    contain every word of the query (so "1 Test" finds "1 Test St").
    """
    _, layers = load_store()
    wanted = _norm(query)
    words = [_norm(w) for w in query.split() if _norm(w)]
    if not wanted:
        return []
    found = {}
    for layer in layers:
        if layer.meta['category'] not in ('parcels', 'addresses'):
            continue
        for attrs, geom in layer.features:
            if geom is None:
                continue
            for key, value in attrs.items():
                if value is None or not re.search(r'addr|civic|street|roll|arn|pin|legal|plan|lot|conc', key, re.I):
                    continue
                norm = _norm(value)
                if not norm:
                    continue
                if norm == wanted:
                    rank = 0
                elif norm.startswith(wanted):
                    rank = 1
                elif words and all(w in norm for w in words):
                    rank = 2
                else:
                    continue
                p = geom.representative_point()
                lat, lon = round(p.y / M_PER_DEG_LAT, 7), round(p.x / M_PER_DEG_LON, 7)
                candidate = {'label': str(value).strip(), 'latitude': lat, 'longitude': lon, 'rank': rank,
                             'matched': {'layer': layer.meta['name'], 'field': key, 'value': value},
                             'kind': layer.meta['category']}
                key_ = (candidate['label'].lower(), round(lat, 4), round(lon, 4))
                if key_ not in found or found[key_]['rank'] > rank:
                    found[key_] = candidate
    # Parcels before address points at equal rank: a parcel carries the lot boundary.
    return sorted(found.values(), key=lambda c: (c['rank'], c['kind'] != 'parcels', len(c['label'])))[:limit]


def find_property(query: str):
    """A point inside the parcel matching an address, roll number or PIN, or None."""
    candidates = search_properties(query, limit=1)
    return candidates[0] if candidates else None


# Colours shared with the web map legend.
CATEGORY_STYLE = {
    'parcels': '#6b7280', 'zoning': '#8c7ca9', 'official_plan': '#c08a3e', 'floodplain': '#2f7fc1',
    'natural_heritage': '#3f8f4f', 'heritage': '#b5523b', 'easements': '#d4a017', 'rail': '#222222',
    'provincial_plans': '#1f9e89', 'servicing': '#0e7490', 'topography': '#a16207', 'addresses': '#525252',
    'neighbourhoods': '#9ca3af', 'other': '#64748b',
}


def map_features(latitude: float, longitude: float, radius_m: float = 250, per_layer: int = 1500) -> dict:
    """GeoJSON of every stored layer around a point, for drawing the lot in context on a map."""
    manifest, layers = load_store()
    if manifest is None:
        return status()
    point = Point(_to_metres(longitude, latitude))
    parcel = None
    for layer in layers:
        if layer.meta['category'] == 'parcels':
            hits = layer.near(point, 0)
            if hits:
                parcel = {'type': 'Feature', 'properties': {**_clean(hits[0][0]), '_layer': layer.meta['name']},
                          'geometry': mapping(_to_wgs84(hits[0][1]))}
                break
    area = point.buffer(radius_m)
    out = []
    for layer in layers:
        if layer.tree is None:
            continue
        features = []
        for i in layer.tree.query(area):
            attrs, geom = layer.features[layer._indexed[int(i)]]
            if not geom.intersects(area):
                continue
            props = _clean(attrs)
            if layer.meta['category'] == 'zoning':
                props['_zone'] = _pick(attrs, r'^zone$', r'zone_?(code|cat|class)?$', r'zon', r'symbol')
            features.append({'type': 'Feature', 'properties': props,
                             'geometry': mapping(_to_wgs84(geom))})
            if len(features) >= per_layer:
                break
        if features:
            category = layer.meta['category'] or 'other'
            out.append({'category': category, 'name': layer.meta['name'], 'source_url': layer.meta['url'],
                        'geometry_type': layer.meta.get('geometry_type'), 'color': CATEGORY_STYLE.get(category),
                        'truncated': len(features) >= per_layer,
                        'features': {'type': 'FeatureCollection', 'features': features}})
    order = list(CATEGORY_STYLE)
    out.sort(key=lambda l: order.index(l['category']) if l['category'] in order else len(order))
    return {'status': 'available', 'center': {'latitude': latitude, 'longitude': longitude}, 'radius_m': radius_m,
            'parcel': parcel, 'layers': out, 'retrieved_at': manifest['retrieved_at']}


DOCUMENT_GROUPS = [
    ('zoning_bylaw', r'zoning|by-?law|zone'),
    ('official_plan', r'official[-_ ]?plan|secondary[-_ ]plan|neighbourhood plan'),
    ('provincial', r'provincial|ontario\.ca|planning statement|greenbelt|moraine|o\. ?reg|060545|planning act'),
    ('heritage_environment', r'heritage|environment|natural|conservation|trca|cloca'),
    ('development_standards', r'sustainab|standard|guideline|site plan|urban design|complete application'),
]


def document_group(doc: dict) -> str:
    label = f"{doc.get('title', '')} {doc.get('url', '')}"
    for group, pattern in DOCUMENT_GROUPS:
        if re.search(pattern, label, re.I):
            return group
    return 'other'


def _grouped_documents(manifest: dict) -> dict:
    grouped = {}
    for doc in manifest['documents']:
        grouped.setdefault(document_group(doc), []).append(doc)
    return grouped


def documents() -> dict:
    """Every stored document, grouped by the framework it belongs to."""
    manifest, _ = load_store()
    if manifest is None:
        return status()
    grouped = {}
    for doc in manifest['documents']:
        grouped.setdefault(document_group(doc), []).append(
            {k: doc.get(k) for k in ('title', 'url', 'file', 'kind', 'pages', 'bytes', 'sha256')})
    for docs in grouped.values():
        docs.sort(key=lambda d: (d['kind'] != 'pdf', d['title'] or ''))
    return {'status': 'available', 'retrieved_at': manifest['retrieved_at'], 'groups': grouped,
            'count': len(manifest['documents'])}


def document_path(file: str) -> Path | None:
    """The stored file for a manifest entry, never anything outside the store."""
    manifest, _ = load_store()
    if manifest is None or file not in {d['file'] for d in manifest['documents']}:
        return None
    path = (store_dir() / file).resolve()
    return path if path.is_file() and store_dir().resolve() in path.parents else None


@lru_cache(maxsize=256)
def _pages(text_file: str, stamp: str) -> list[str]:
    return json.loads((store_dir() / text_file).read_text(encoding='utf-8'))


def _snippet(text: str, match: re.Match, width: int = 160) -> str:
    start, end = max(0, match.start() - width), min(len(text), match.end() + width)
    return ('…' if start else '') + ' '.join(text[start:end].split()) + ('…' if end < len(text) else '')


def search_documents(query: str, limit: int = 50) -> dict:
    """Full-text search over every stored PDF page: the by-laws, plans and regulations."""
    manifest, _ = load_store()
    if manifest is None:
        return status()
    if not query.strip():
        return {'status': 'available', 'query': query, 'results': []}
    pattern = re.compile(re.escape(query.strip()), re.I)
    stamp, results = manifest['retrieved_at'], []
    for doc in manifest['documents']:
        if not doc.get('text_file'):
            continue
        for number, text in enumerate(_pages(doc['text_file'], stamp), 1):
            match = pattern.search(text)
            if match:
                results.append({'title': doc['title'], 'url': doc['url'], 'file': doc['file'], 'page': number,
                                'group': document_group(doc), 'snippet': _snippet(text, match),
                                'hits_on_page': len(pattern.findall(text))})
    results.sort(key=lambda r: (r['group'] != 'zoning_bylaw', -r['hits_on_page']))
    return {'status': 'available', 'query': query, 'total': len(results), 'results': results[:limit]}


def _document_refs(manifest: dict, zone_codes: list[str], bylaw_numbers: list[str]) -> list[dict]:
    """Downloaded documents that name this parcel's by-law, and the pages (with text) that mention its zone."""
    refs = []
    for doc in manifest['documents']:
        label = f"{doc['title']} {doc['url']}"
        named = [n for n in bylaw_numbers if re.search(rf'(?<!\d){re.escape(n)}(?!\d)', label)]
        if not (named or document_group(doc) == 'zoning_bylaw'):
            continue
        ref = {'title': doc['title'], 'url': doc['url'], 'file': doc['file'], 'names_parcel_bylaw': named,
               'zone_pages': {}, 'excerpts': []}
        if doc.get('text_file') and zone_codes:
            pages = _pages(doc['text_file'], manifest['retrieved_at'])
            for code in zone_codes:
                pattern = re.compile(rf'(?<![A-Za-z0-9-]){re.escape(code)}(?![A-Za-z0-9])')
                for number, text in enumerate(pages, 1):
                    match = pattern.search(text)
                    if not match:
                        continue
                    ref['zone_pages'].setdefault(code, []).append(number)
                    if len(ref['excerpts']) < 12:
                        ref['excerpts'].append({'zone': code, 'page': number, 'text': _snippet(text, match)})
        if named or ref['zone_pages']:
            refs.append(ref)
    return sorted(refs, key=lambda r: (not r['names_parcel_bylaw'], -sum(map(len, r['zone_pages'].values()))))


# Zone standards a by-law states as numbers, and the words that name them.
PROVISIONS = [
    ('permitted_uses', r'permitted uses?|uses? permitted'),
    ('lot_frontage', r'lot frontage|frontage'),
    ('lot_area', r'lot area'),
    ('front_yard', r'front yard|front setback'),
    ('side_yard', r'side yard|interior side|exterior side|flankage'),
    ('rear_yard', r'rear yard|rear setback'),
    ('building_height', r'height|storeys?'),
    ('lot_coverage', r'lot coverage|coverage'),
    ('floor_area', r'floor (space|area) (index|ratio)|gross floor area|\bfsi\b|\bgfa\b'),
    ('landscaping', r'landscap|open space'),
    ('parking', r'parking|loading'),
    ('dwelling_units', r'dwelling units?|units? per|density|accessory dwelling|second(ary)? (suite|unit)|garden suite'),
]
MEASURE = re.compile(r'\d+(?:[.,]\d+)?\s*(?:m2|m²|sq\.? ?m|square metres?|metres?|m\b|%|per ?cent|storeys?|spaces?|units?|ha|hectares?)', re.I)


def zone_variants(codes: list[str]) -> list[str]:
    """Each zone code, its base and its exception numbers: "R4-12" and "R4(X12)" fall under R4, and X12."""
    out = []
    for code in codes:
        # Pickering numbers site-specific exceptions X1, X2, …; each has its own section.
        exceptions = re.findall(r'\bX\d+\b', code.upper().replace('-', ' '))
        for variant in (code, re.split(r'[-(/\s]', code)[0], *exceptions):
            if variant and variant not in out:
                out.append(variant)
    return out


def zone_provisions(manifest: dict, zone_codes: list[str], per_kind: int = 6) -> dict:
    """Lines of the stored by-laws that state a measured standard on a page naming this zone.

    Text extraction, not interpretation: each line comes with its document and page
    so it can be read in context, and "minimum" / "maximum" is reported only when
    the line says so.
    """
    found = {kind: [] for kind, _ in PROVISIONS}
    if not zone_codes:
        return found
    zone_pattern = re.compile('|'.join(rf'(?<![A-Za-z0-9-]){re.escape(c)}(?![A-Za-z0-9])' for c in zone_codes))
    for doc in manifest['documents']:
        if not doc.get('text_file') or document_group(doc) != 'zoning_bylaw':
            continue
        for number, text in enumerate(_pages(doc['text_file'], manifest['retrieved_at']), 1):
            if not zone_pattern.search(text):
                continue
            for line in (' '.join(l.split()) for l in text.splitlines()):
                if len(line) < 6 or len(line) > 400:
                    continue
                for kind, pattern in PROVISIONS:
                    if len(found[kind]) >= per_kind or not re.search(pattern, line, re.I):
                        continue
                    measures = MEASURE.findall(line)
                    if kind != 'permitted_uses' and not measures:
                        continue
                    bound = ('minimum' if re.search(r'\bmin(imum)?\b', line, re.I) else
                             'maximum' if re.search(r'\bmax(imum)?\b', line, re.I) else None)
                    found[kind].append({'text': line, 'measures': measures, 'bound': bound, 'page': number,
                                        'file': doc['file'], 'title': doc['title']})
                    break
    return found


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

    # A zone only touching the lot boundary is a neighbour, not the lot's zone.
    near_zones = against('zoning', 30)
    zoning = [h for h in near_zones if h['distance_m'] == 0 and (h['parcel_share_pct'] is None or h['parcel_share_pct'] >= 1)]
    adjacent = [h for h in near_zones if h not in zoning]
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
    searched_codes = zone_variants(zone_codes)
    adjacent_zones = sorted({z for h in adjacent if (z := _pick(h['attributes'], r'^zone$', r'zone_?(code|cat|class)?$',
                                                                r'zon', r'symbol'))} - set(zone_codes))

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
                'zone_standards_in_bylaw_text': zone_provisions(manifest, searched_codes),
            },
            '4_site_characteristics': {
                'servicing_nearby': servicing, 'topography': topography,
                'natural_heritage': overlays['natural_heritage'],
                'adjacent_zoning': adjacent, 'adjacent_zone_codes': adjacent_zones,
                'applicant_must_supply': ['Topographic survey (grades, slopes)', 'Servicing confirmation',
                                          'Adjacent land uses (adjacent zoning from City data is listed here)'],
            },
            '5_supporting_documents': {
                'always': ['Planning justification report', 'Concept site plan', 'Survey or reference plan'],
                'triggered_by_overlays': {c: OVERLAY_STUDIES[c] for c in triggered},
                'by_scale': ['Traffic impact study (larger developments)',
                             'Functional servicing report', 'Archaeological assessment (if required)'],
                'reference': 'O. Reg. 545/06 (complete application) and the City pre-consultation checklist',
            },
            '6_planning_frameworks': {
                'zoning_bylaw_references': _document_refs(manifest, searched_codes, bylaw_numbers),
                'official_plan_designation': [_pick(h['attributes'], r'desig', r'land_?use', r'name')
                                              for h in official_plan],
                'provincial': ['Provincial Planning Statement (2024)'] +
                              [h['layer'] for h in overlays['provincial_plans']],
                'all_documents': {group: [{'title': d['title'], 'url': d['url'], 'file': d['file'],
                                           'pages': d.get('pages')} for d in docs]
                                  for group, docs in _grouped_documents(manifest).items()},
            },
        },
    }
