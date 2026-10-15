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
import threading
from functools import lru_cache
from pathlib import Path

import shapely
import shapely.ops
from shapely import STRtree
from shapely.geometry import Point, mapping

from engine import dev_charges, lot_rules

DEFAULT_STORE = Path(__file__).parent.parent / 'data' / 'municipal' / 'pickering'
FIGURE_SETBACKS = Path(__file__).parent.parent / 'data' / 'pickering_figure_setbacks.json'

# Geometry is kept in local metres around Pickering (equirectangular; error is
# well under 1% across the city) so areas and distances read in m.
REF_LAT = 43.85
M_PER_DEG_LAT = 111_132.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(REF_LAT))
SCALE = (M_PER_DEG_LON, M_PER_DEG_LAT)
# West, south, east, north in WGS84: the City with a margin (the scraper clips to the same box).
CITY_BOUNDS = (-79.23, 43.79, -78.95, 44.04)

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
                geom = shapely.from_geojson(json.dumps(feature['geometry']))
                # Regional and provincial layers come as region-wide shapes of a million points;
                # only the part over the City is ever looked at.
                if shapely.get_num_coordinates(geom) > 20_000:
                    geom = shapely.clip_by_rect(geom, *CITY_BOUNDS)
                geom = shapely.transform(geom, lambda xy: xy * SCALE)
            except Exception:
                continue
            if geom is None or geom.is_empty:
                self.features.append((feature['properties'], None))
                continue
            if not geom.is_valid:
                geom = shapely.make_valid(geom)  # buffer(0) took minutes on the regional stream polygons
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


@lru_cache(maxsize=1)
def _rules(store: str, stamp: str, file: str | None) -> dict:
    path = Path(store) / file if file else None
    if path is None or not path.exists():
        return {'zones': {}, 'exceptions': {}, 'missing_file': True}
    rules = json.loads(path.read_text(encoding='utf-8'))
    # The setbacks an exception draws instead of stating, read by eye from its figure; the by-law text only points at them.
    for exception, figures in json.loads(FIGURE_SETBACKS.read_text(encoding='utf-8')).items():
        if exception in rules['exceptions']:
            rules['exceptions'][exception]['figures'] = figures
    return rules


def zone_rules() -> dict:
    """The by-law's zone standards and exceptions for the stored snapshot (scripts/zone_rules.py)."""
    manifest, _ = load_store()
    if manifest is None:
        return {'zones': {}, 'exceptions': {}, 'missing_file': True}
    root = store_dir()
    return _rules(str(root), str((root / 'manifest.json').stat().st_mtime_ns), manifest.get('zone_rules_file'))


ZONE_FIELD = (r'^zone$', r'zone_?(code|cat|class)?$', r'zon', r'symbol')
# Fields that hold a zone symbol, strictly: an overlay such as "Intake Protection Zones" has none,
# so it never governs a lot.
ZONE_CODE_FIELD = (r'^zone$', r'^zon(e|ing)_?(code|cat|category|class|symbol)$')


_LOAD_LOCK = threading.Lock()


def _lot_fabric(layers):
    """The parcel layer with the most features: the lots. The others are the City's outline and the
    township survey grid."""
    return max((l for l in layers if l.meta['category'] == 'parcels'), key=lambda l: len(l.features), default=None)


def _is_lane(attrs: dict) -> bool:
    """A road the City names a lane ("Four Seasons Lane"): behind a lot, it is the lot's rear lane."""
    # Its suffix is "Lane", or its full name ends in one; a street named "Lane Road" is not a lane.
    return any(re.fullmatch(r'lane|laneway|ln', str(value).strip(), re.I) if re.search(r'suffix|sfx', key, re.I)
               else re.search(r'\s(lane|laneway|ln)$', str(value).strip(), re.I)
               for key, value in attrs.items() if value and re.search(r'name|suffix|sfx|street|label', key, re.I))


def _streets_and_lanes(layers, geom, reach: float) -> tuple[list, list]:
    """Road centrelines within reach of a lot, the lanes apart from the streets."""
    streets, lanes = [], []
    for layer in _street_layers(layers):
        for i in layer.tree.query(geom.buffer(reach)):
            attrs, road = layer.features[layer._indexed[int(i)]]
            (lanes if _is_lane(attrs) else streets).append(road)
    return streets, lanes


def _footprints(layers, geom) -> list:
    """The City's building footprints on a lot (it publishes the same layer under several services)."""
    layer = next((l for l in layers if l.tree is not None and re.fullmatch(r'buildings?', l.meta['name'], re.I)), None)
    return [layer.features[layer._indexed[int(i)]][1] for i in layer.tree.query(geom)] if layer else []


# Which by-law uses each EnerZen unit is built as.
ENERZEN_UNITS = {'Garden Suite': r'^Additional Dwelling Unit', '3-Bedroom house': r'^Detached Dwelling',
                 'Townhouse': r'^(Street|Block) Townhouse|^Multiple Attached', 'MURB': r'^Apartment'}


def permitted_uses(code, rules) -> dict | None:
    """The dwellings the zone's permitted-use table marks, and which EnerZen units they fit; None for a
    zone with no column in those tables (an exception zone's uses are in its own text)."""
    base = lot_rules.split_zone(code)[0] if code else None
    uses = (rules.get('uses') or {}).get(base)
    if not uses:
        return None
    first = next(iter(uses.values()))
    dwellings = sorted(u for u in uses if re.search(r'dwelling|townhouse|apartment|duplex', u, re.I))
    return {'zone': base, 'dwellings': dwellings, 'other_uses': len(uses) - len(dwellings),
            'enerzen_units': [unit for unit, pattern in ENERZEN_UNITS.items() if any(re.search(pattern, u) for u in uses)],
            'document': first.get('document'), 'file': first.get('file'), 'page': first.get('page')}


def additional_units(layers, geom, code, rules, overlays, standards, urban: bool | None = None) -> dict | None:
    """Can this lot take a garden suite (an additional dwelling unit in an accessory building)?

    From the by-law's own permitted-use tables and its section 4.3 (or Seaton's 14.2.9), read by
    scripts/zone_rules.py; None when the zone has no row in those tables.
    """
    aru = rules.get('additional_units') or {}
    base, exceptions = lot_rules.split_zone(code) if code else (None, [])
    zone = aru.get('zones', {}).get(base)
    basis = 'use_table'
    if zone is None:
        # An exception zone has no row in the use tables. Planning Act s.35.1 permits a unit in an
        # ancillary building wherever a detached, semi-detached or row house is permitted on urban
        # residential land, so the exception's own text decides.
        text = next((e for x in exceptions if (e := rules.get('exceptions', {}).get(x))
                     and re.search(r'detached|townhouse|row ?house', e.get('text', ''), re.I)), None)
        if text is None:
            return None
        zone, basis = {'permitted': True, 'seaton': False, **{k: text.get(k) for k in ('document', 'file', 'page')}}, 'planning_act'
    number = '14.2.9' if zone['seaton'] else '4.3'
    section = aru.get('sections', {}).get(number) or {}
    cite = lambda s: {'document': s.get('document'), 'page': s.get('page'), 'file': s.get('file')}
    out = {'zone': base, 'permitted_in_zone': zone['permitted'], 'basis': basis, 'zone_table': cite(zone),
           'section': {**cite(section), 'number': number}, 'blockers': [], 'checks': []}
    if not zone['permitted']:
        return out
    on_lot = lambda c, pattern='': [h for h in overlays.get(c, []) if h['distance_m'] == 0
                                    and re.search(pattern, h['layer'], re.I)]
    # A plan area over the whole lot rules a garden suite out; over part of it, the suite sits outside that part.
    for name, hits, rule in (
            ('the Oak Ridges Moraine', on_lot('provincial_plans', r'moraine'),
             'only one additional unit, inside the house'),
            ('Greenbelt Protected Countryside', [h for h in on_lot('provincial_plans', r'greenbelt')
                                                 if h['attributes'].get('DESIGNATION') == 'Protected Countryside'],
             'only in an accessory building legally built by July 1, 2017')):
        share = max((h['parcel_share_pct'] or 0 for h in hits), default=0)
        if share >= 95:
            out['blockers'].append(f'In {name}: {rule}.')
        elif share > 0:
            out['checks'].append(f'{share:g}% of the lot is in {name} ({rule}); a new garden suite must sit outside it.')
    if basis == 'planning_act' and urban is False:
        out['permitted_in_zone'] = None
        out['checks'].append(f"Exception zone {', '.join(exceptions)}: outside the urban area Planning Act s.35.1 does "
                             "not apply, so only the exception's own text can permit a garden suite.")
        return out
    if basis == 'planning_act':
        out['checks'].append(f"Exception zone {', '.join(exceptions)} permits houses and the lot is in the urban area, "
                             'so Planning Act s.35.1 permits a garden suite.')
    if on_lot('floodplain', r'regulat'):
        out['checks'].append('In the conservation authority regulated area: no additional unit on hazardous lands; '
                             'the authority confirms where the hazard limit falls.')
    if on_lot('natural_heritage'):
        out['checks'].append('A mapped natural heritage feature touches the lot: no garden suite inside a key '
                             'natural heritage or hydrologic feature.')
    if geom is None or not section:
        return out
    area = geom.area
    large = area > section.get('large_lot_m2', float('inf'))
    height = section.get('max_height_large_lot_m' if large else 'max_height_m')
    houses = _footprints(layers, geom)
    built = sum(h.intersection(geom).area for h in houses)
    coverage = (standards.get('standards', {}).get('lot_coverage') or {}).get('value') or section.get('default_coverage_pct')
    room = round(area * coverage / 100 - built, 1) if coverage else None
    out.update({
        'max_height_m': height, 'min_interior_side_m': section.get('min_interior_side_m'),
        'min_rear_m': section.get('min_rear_m'),
        'taller_than_m': section.get('taller_than_m'), 'min_side_rear_if_taller_m': section.get('min_side_rear_if_taller_m'),
        'max_floor_area_m2': section.get('max_floor_area_m2'),
        'max_share_of_house_pct': section.get('max_share_of_house_pct'),
        'coverage_pct': coverage, 'existing_footprint_m2': round(built, 1),
        'footprint_left_m2': max(room, 0) if room is not None else None,
        'path_width_m': section.get('path_width_m'),
        'path_fits': _path_fits(layers, geom, houses, section.get('path_width_m')),
        'existing_units': _existing_units(layers, geom),
    })
    if room is not None and room <= 0:
        out['blockers'].append(f'The buildings already cover the {coverage:g}% of the lot the zone allows.')
    if out['path_fits'] is False:
        out['blockers'].append(f"No {section.get('path_width_m'):g} m clear path from the street past the house "
                               'to the rear yard, as the by-law requires.')
    return out


def _path_fits(layers, geom, houses, width) -> bool | None:
    """Whether a path of the given width runs from the street side of the lot to behind its buildings."""
    streets, _ = _streets_and_lanes(layers, geom, lot_rules.FRONTING_M + 100)
    if not houses or not streets or not width:
        return None
    road = min(streets, key=lambda g: g.distance(geom))
    house = shapely.union_all(houses).intersection(geom)
    if house.area <= 0:  # a neighbour's footprint only touching the lot line
        return None
    behind = geom.difference(road.buffer(max(road.distance(Point(c)) for c in shapely.get_coordinates(house))))
    if behind.is_empty:
        return False
    # Shrinking the open ground by half the width leaves only the parts a path that wide can reach.
    open_ground = geom.difference(house).buffer(-width / 2)
    front = road.distance(geom) + width
    parts = getattr(open_ground, 'geoms', [open_ground])
    return any(p.distance(road) <= front and p.intersects(behind) for p in parts if not p.is_empty)


def _existing_units(layers, geom) -> int:
    """Additional dwelling units the City has addressed on this lot."""
    return sum(len(l.tree.query(geom, predicate='intersects')) for l in layers
               if l.tree is not None and re.search(r'accessory ?dwelling', l.meta['name'], re.I))


def _apply_rules(layers, geom, code, rules) -> tuple[dict, dict | None]:
    """A lot's standards and dimensions, using its streets, any rear lane and its building's footprint."""
    streets, lanes = _streets_and_lanes(layers, geom, lot_rules.FRONTING_M + 100) if geom is not None else ([], [])
    dims = lot_dimensions(geom, streets or lanes)
    attached = lot_rules.attached_sides(geom, dims['rotation_deg'], _footprints(layers, geom)) if dims else []
    lot = lot_rules.apply_to_lot(geom, code, rules, streets, dims, lanes, attached, _neighbour_zones(layers, geom))
    if lot['basis'] == 'figure' and lot['figure_setbacks'] and dims:
        _sides_from_figures(layers, geom, lot, dims)
    return lot, dims


COMPASS = {'north': 'N', 'south': 'S', 'east': 'E', 'west': 'W'}


def _sides_from_figures(layers, geom, lot: dict, dims: dict):
    """Give a lot its yards from the drawing its exception sets them on.

    The drawing sets each setback from a street or from a named edge of the whole block ("south lot
    line"), not from each lot in it. A side facing a street the drawing names takes that street's
    setback; a side on the block's edge takes the setback of the edge in that direction; a side
    inside the block faces neither, and the drawing asks nothing of it. Where an exception draws
    several parts with different setbacks for the same line, the larger is taken.
    """
    rotation, centre = dims['rotation_deg'], geom.centroid
    numbers = [int(x[1:]) for x in lot['exceptions']]
    block = [g for l in layers if l.meta['category'] == 'zoning' and l.tree is not None
             for i in l.tree.query(geom)
             for attrs, g in [l.features[l._indexed[int(i)]]]
             if (n := re.findall(r'\d+', str(_pick(attrs, r'^exception') or ''))) and int(n[0]) in numbers]
    block = shapely.union_all([g.buffer(0.5) for g in block]).buffer(-0.5) if block else None
    on_edge = set()
    if block is not None and not block.is_empty:
        near_edge = block.boundary.buffer(1.5)
        ring = list((geom.geoms[0] if hasattr(geom, 'geoms') else geom).exterior.coords)
        for a, b in zip(ring, ring[1:]):  # each edge on its own: along the block's edge, they join at the corners
            segment = shapely.geometry.LineString([a, b])
            if segment.length > 2 and segment.intersection(near_edge).length >= segment.length / 2:
                on_edge.add(lot_rules._side_of(centre, segment.interpolate(0.5, normalized=True), rotation))
    named = [(str(_pick(a, r'^full_?name$', r'^name$') or ''), g) for l in _street_layers(layers)
             for i in l.tree.query(geom.buffer(lot_rules.FRONTING_M + 10)) for a, g in [l.features[l._indexed[int(i)]]]]
    found = {}
    for figure in lot['figure_setbacks']:
        for setback in figure['setbacks']:
            line, value = setback['from'].lower(), setback['value_m']
            sides = {lot_rules._side_of(centre, g, rotation) for name, g in named
                     if name and name.lower() in line and g.distance(geom) <= lot_rules.FRONTING_M + 10}
            if not sides and 'lot line' in line and not re.search(r'\b(zone|item|block|plan|parcel|bank|with)\b|\d', line):
                sides = {COMPASS[w] for w in re.findall(r'north|south|east|west', line)} & on_edge
            for side in sides:
                found.setdefault(side, []).append((value, f"{figure['figure']}: {setback['stated']} from {setback['from']}"))
    for side, entry in lot['setbacks_by_side'].items():
        if entry['value'] is not None:
            continue
        if side in found:
            value, said = max(found[side])
            entry.update(value=round(value, 2), note=f"Exception {', '.join(lot['exceptions'])}, {said}"
                         + ('; the drawing gives other parts other setbacks, and the larger is shown' if len({v for v, _ in found[side]}) > 1 else ''))
        elif block is not None and side not in on_edge:
            entry.update(value=0.0, note="Inside the block the exception's drawing covers: it sets setbacks only from "
                                         "the block's outer lines and streets.")
    if all(e['value'] is not None for e in lot['setbacks_by_side'].values()):
        envelope = lot_rules._envelope(geom, rotation, {s: lot['setbacks_by_side'][s]['value'] for s in 'NESW'})
        lot.update(complete=True, basis='figure_mapped', _envelope=envelope,
                   buildable_area_m2=round(envelope.area, 1) if envelope is not None else None,
                   basis_note="Yards read from the exception's drawing, side by side; see each side's note.")


def _neighbour_zones(layers, geom) -> dict:
    """The zones a lot abuts (within a metre of its boundary, other than the zone it sits in), each
    with the shapes it has there, so a yard the by-law sets apart beside one zone finds its side."""
    found = {}
    if geom is None:
        return found
    edge, inside = geom.buffer(1.0), geom.representative_point()
    for layer in (l for l in layers if l.meta['category'] == 'zoning' and l.tree is not None):
        for i in layer.tree.query(edge):
            attrs, zone_geom = layer.features[layer._indexed[int(i)]]
            code = _zone_code(attrs)
            if code and zone_geom.intersects(edge) and not zone_geom.contains(inside):
                found.setdefault(lot_rules.split_zone(code)[0], []).append(zone_geom)
    return found


def _street_layers(layers) -> list:
    """Road centrelines, which say where a street runs. The City's other "road" layers are curbs,
    labels and streetlights, and a curb near a side lot line made most lots look like corner lots."""
    roads = [l for l in layers if l.meta['category'] == 'roads' and l.tree is not None]
    return [l for l in roads if re.search(r'cent(re|er) ?line', l.meta['name'], re.I)] or roads


def load_store():
    """(manifest, layers), or (None, []) before the first scrape. Reloads after a re-scrape."""
    root = store_dir()
    manifest = root / 'manifest.json'
    if not manifest.exists():
        return None, []
    # One load at a time: lru_cache lets every request that arrives during the first load start its
    # own, and a few copies of the City's layers at once is more memory than the server has.
    with _LOAD_LOCK:
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
    report = manifest.get('completeness') or {}
    return {'status': 'available', 'retrieved_at': manifest['retrieved_at'], 'layers': by_category,
            'documents': len(manifest['documents']), 'errors': manifest['errors'],
            'catalog_layers': manifest.get('catalog_layers'),
            'council_amendments': sum(1 for d in manifest['documents'] if d.get('source') == 'council'),
            'completeness': {
                'complete': report.get('complete'),
                'incomplete_layers': report.get('incomplete_layers', []),
                'not_downloaded': report.get('not_downloaded', []),
                'missing_bylaws': report.get('missing_bylaws', []),
                'pdfs_with_blank_pages': len(report.get('pdfs_with_blank_pages', [])),
                'documents_carried_over': len(report.get('documents_carried_over', [])),
                'errors': len(manifest['errors']),
            }}


def _clean(attrs: dict) -> dict:
    return {k: v for k, v in attrs.items() if v not in (None, '', ' ')
            and not re.fullmatch(r'(objectid|fid|shape[._]?\w*|globalid|st_\w+)', k, re.I)}


def _pick(attrs: dict, *patterns) -> str | None:
    for pattern in patterns:
        for key, value in attrs.items():
            if value not in (None, '') and re.search(pattern, key, re.I):
                return str(value).strip()
    return None


def _legal_description(layers, geom, attrs: dict) -> str | None:
    """The parcel's own legal description, or, where the City's parcel has none, one built from its
    layers: the registered plan of the subdivision the lot is in (Major Residential Developments) and
    the geographic township lot and concession (Ontario's lot fabric), said to be built that way."""
    own = _pick(attrs, r'legal|plan|lot|conc')
    if own or geom is None:
        return own
    point, plan, township = geom.representative_point(), None, None
    for layer in layers:
        first = layer.features[0][0] if layer.tree is not None and layer.features else {}
        if not ({'PLAN_NO', 'LOT_IDENT'} & set(first)):
            continue
        for i in layer.tree.query(point):
            a, shape = layer.features[layer._indexed[int(i)]]
            if not shape.contains(point):
                continue
            if plan is None and a.get('PLAN_NO'):
                plan = f"Registered Plan {a['PLAN_NO']}"
            if township is None and a.get('LOT_IDENT') and a.get('CONCESSION_IDENT'):
                concession = re.sub(r'^CON\b\.?', 'Concession', str(a['CONCESSION_IDENT']).strip(), flags=re.I)
                township = (f"Part of {str(a['LOT_IDENT']).strip().title()}, {concession.title()}, Geographic Township "
                            f"of {str(a.get('GEOGRAPHIC_TOWNSHIP_NAME') or 'Pickering').title()}")
    parts = [p for p in (plan, township) if p]
    return f"{'; '.join(parts)} (from the City's subdivision and lot fabric layers)" if parts else None


def _to_wgs84(geom):
    return shapely.transform(geom, lambda xy: xy / SCALE)


def _label(attrs: dict) -> str | None:
    return _pick(attrs, r'full_?addr', r'addr', r'civic', r'legal', r'roll|arn', r'\bpin\b|^pin')


SEARCH_FIELD = re.compile(r'addr|civic|street|roll|arn|pin|legal|plan|lot|conc', re.I)


@lru_cache(maxsize=1)
def _property_index(store: str, stamp: str) -> list[tuple]:
    """(normalized value, label, field, layer, category, lat, lon) for every searchable parcel and address field."""
    _, layers = load_store()
    index = []
    for layer in layers:
        if layer.meta['category'] not in ('parcels', 'addresses'):
            continue
        fields = None
        for attrs, geom in layer.features:
            if geom is None:
                continue
            if fields is None:
                fields = [k for k in attrs if SEARCH_FIELD.search(k)]
            point = None
            for key in fields:
                value = attrs.get(key)
                norm = _norm(value) if value is not None else ''
                if not norm:
                    continue
                if point is None:
                    p = geom.representative_point()
                    point = (round(p.y / M_PER_DEG_LAT, 7), round(p.x / M_PER_DEG_LON, 7))
                index.append((norm, str(value).strip(), key, layer.meta['name'], layer.meta['category'], *point))
    return index


def search_properties(query: str, limit: int = 8) -> list[dict]:
    """Parcels and address points matching an address, roll number, PIN or legal description, best first.

    Exact matches rank before prefix matches, which rank before matches that only
    contain every word of the query (so "1 Test" finds "1 Test St").
    """
    wanted = _norm(query)
    words = [_norm(w) for w in query.split() if _norm(w)]
    if not wanted or load_store()[0] is None:
        return []
    root = store_dir()
    found = {}
    for norm, label, key, layer, category, lat, lon in _property_index(str(root), str((root / 'manifest.json').stat().st_mtime_ns)):
        if norm == wanted:
            rank = 0
        elif norm.startswith(wanted):
            rank = 1
        elif words and all(w in norm for w in words):
            rank = 2
        else:
            continue
        dedupe = (label.lower(), round(lat, 4), round(lon, 4))
        if dedupe not in found or found[dedupe]['rank'] > rank:
            found[dedupe] = {'label': label, 'latitude': lat, 'longitude': lon, 'rank': rank, 'kind': category,
                             'matched': {'layer': layer, 'field': key, 'value': label}}
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
    'neighbourhoods': '#9ca3af', 'roads': '#a8a29e', 'other': '#64748b',
}


def map_features(latitude: float, longitude: float, radius_m: float = 250, per_layer: int = 1500) -> dict:
    """GeoJSON of every stored layer around a point, for drawing the lot in context on a map."""
    manifest, layers = load_store()
    if manifest is None:
        return status()
    point = Point(_to_metres(longitude, latitude))
    # The smallest parcel at the point is the lot (see lookup).
    at_point = [(attrs, geom, layer) for layer in layers if layer.meta['category'] == 'parcels'
                for attrs, geom, _ in layer.near(point, 0)]
    parcel = None
    if at_point:
        attrs, geom, layer = min(at_point, key=lambda hit: hit[1].area)
        parcel = {'type': 'Feature', 'properties': {**_clean(attrs), '_layer': layer.meta['name']},
                  'geometry': mapping(_to_wgs84(geom))}
    area = point.buffer(radius_m)
    # A shape far larger than the view (a floodplain, a land-use designation) is cut to twice the
    # view, or one lot's map would carry tens of megabytes of the rest of the city.
    view = point.buffer(radius_m * 2).bounds
    out, drawn, fabric = [], set(), _lot_fabric(layers)
    for layer in layers:
        # The City publishes the same roads, buildings and address points under several services, and
        # its own outline as a parcel: each layer is drawn once, and only the lot fabric as parcels.
        same = (layer.meta['name'], len(layer.features))
        if layer.tree is None or same in drawn or (layer.meta['category'] == 'parcels' and layer is not fabric):
            continue
        drawn.add(same)
        features = []
        for i in layer.tree.query(area):
            attrs, geom = layer.features[layer._indexed[int(i)]]
            if not geom.intersects(area):
                continue
            if shapely.get_num_coordinates(geom) > 400:
                geom = shapely.clip_by_rect(geom, *view)
                if geom.is_empty:
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


def _zone_code(attrs: dict) -> str | None:
    """A zoning polygon's symbol with its exception numbers appended ("R4-X12"), as lot_rules reads it."""
    code = _pick(attrs, *ZONE_CODE_FIELD)
    if not code:
        return None
    numbers = re.findall(r'\d+', _pick(attrs, r'^exception') or '')
    return '-'.join([code] + [f'X{int(n)}' for n in numbers])


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
        exceptions = [f'X{int(n)}' for n in re.findall(r'\bX\s?(\d+)\b', code.upper().replace('-', ' '))]
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


def _lot_concession(text: str) -> set[tuple[str, str]]:
    """(lot, concession) pairs in a legal description or by-law text: "Part of Lot 22, Concession 4"."""
    pairs = set()
    for match in re.finditer(r'\bLots? (\d+)(?:\s*(?:and|&|,)\s*(\d+))?,?\s*(?:\w+\s){0,3}?Con(?:cession|c?\.?)\s*(\w+)', text, re.I):
        for lot in filter(None, match.groups()[:2]):
            pairs.add((lot, match.group(3).upper().rstrip('.')))
    return pairs


def lot_amendments(manifest: dict, property_id: dict | None, zone_codes: list[str]) -> list[dict]:
    """Council zoning amendments whose text names this lot: its address, lot and concession, or exception zone."""
    property_id = property_id or {}
    address = property_id.get('address')
    pairs = _lot_concession(property_id.get('legal_description') or '')
    exceptions = [c for c in zone_codes if re.fullmatch(r'X\d+', c) or re.search(r'[-(]', c)]
    found = []
    for doc in manifest['documents']:
        if doc.get('source') != 'council' or not doc.get('text_file'):
            continue
        text = ' '.join(_pages(doc['text_file'], manifest['retrieved_at']))
        reasons = []
        if address and len(_norm(address)) > 4 and _norm(address) in _norm(text):
            reasons.append(f'names {address}')
        shared = pairs & _lot_concession(text)
        if shared:
            reasons.append('names ' + ', '.join(f'Lot {l}, Concession {c}' for l, c in sorted(shared)))
        for code in exceptions:
            if re.search(rf'(?<![A-Za-z0-9-]){re.escape(code)}(?![A-Za-z0-9])', text):
                reasons.append(f'names zone {code}')
        if reasons:
            found.append({'title': doc['title'], 'url': doc['url'], 'file': doc['file'],
                          'meeting': doc.get('meeting'), 'reasons': reasons})
    return found


def lot_dimensions(parcel_geom, roads: list) -> dict | None:
    """The lot as the site planner sees it: E-W width, N-S depth, and which side faces the street.

    Sides come from the lot's minimum rotated rectangle, the one nearer east-west
    taken as the width; the street side is the direction of the nearest road.
    """
    if parcel_geom is None or parcel_geom.area <= 0:
        return None
    rect = parcel_geom.minimum_rotated_rectangle
    xs, ys = rect.exterior.coords.xy
    edges = [(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) for i in range(2)]
    lengths = [math.hypot(dx, dy) for dx, dy in edges]
    # By direction, not by reach: a long edge at 53 degrees reaches further east than a short one at 37.
    ew = 0 if abs(edges[0][0]) / lengths[0] >= abs(edges[1][0]) / lengths[1] else 1
    rotation = math.degrees(math.atan2(edges[ew][1], edges[ew][0])) % 180
    result = {'width_m': round(lengths[ew], 1), 'depth_m': round(lengths[1 - ew], 1),
              'rotation_deg': round(rotation if rotation <= 90 else rotation - 180, 1),
              'rectangularity': round(parcel_geom.area / rect.area, 2), 'street_side': None}
    if roads:
        centre = parcel_geom.centroid
        nearest = min(roads, key=lambda g: g.distance(parcel_geom))  # the side actually nearest a road
        result['street_side'] = lot_rules._side_of(centre, nearest, result['rotation_deg'])
        result['street_distance_m'] = round(nearest.distance(parcel_geom), 1)
    return result


def setback_summary(standards: dict) -> str | None:
    """"front 6 m (S), rear 7.5 m (N), sides 1.2 m" for the workspace's short parcel card."""
    parts = []
    order = ('front_yard', 'rear_yard', 'exterior_side_yard', 'interior_side_yard')
    for side, entry in sorted(standards['setbacks_by_side'].items(), key=lambda kv: order.index(kv[1]['applies'])):
        if entry['value'] is not None:
            parts.append(f"{entry['applies'].replace('_yard', '').replace('_', ' ')} {entry['value']:g} m ({side})")
    return ', '.join(parts) or None


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

    # The smallest parcel at the point is the lot: the City also publishes its own outline and the
    # township survey grid as parcel layers, and both contain every lot.
    parcels = sorted(hits('parcels'), key=lambda h: h['_geom'].area)
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

    # The zone covering most of the lot governs it; its standards come from the by-law's tables.
    primary_zone = next((code for h in zoning if (code := _zone_code(h['attributes']))), None)
    rules = zone_rules()
    standards, dimensions = _apply_rules(layers, parcel['_geom'] if parcel else None, primary_zone, rules)
    envelope = standards.pop('_envelope')
    # Durham publishes no water or sewer mains; the City's urban area is where the Regional Official
    # Plan plans full municipal services, and outside it a home is on a private well and septic system.
    # The Region supplies the services, so its Official Plan's urban area decides; the City's own outline
    # (wider in places, such as the Rouge valley estates) is used only when the Region's is not stored.
    covers = lambda pattern: [h for h in official_plan if re.search(pattern, h['layer'], re.I)]
    regional = covers(r'^Map \d.* - Urban Area$')
    urban = [h for h in regional or covers(r'AMD_UrbanArea$') if (h['parcel_share_pct'] or 0) >= 50]
    hamlet = [h for h in covers(r'hamlets?$') if (h['parcel_share_pct'] or 0) >= 50]
    servicing_status = {
        'municipal_expected': bool(urban), 'in_urban_area': bool(urban), 'in_hamlet': bool(hamlet),
        'source': (urban or hamlet or [{}])[0].get('source_url'),
        'note': ('Inside the urban area, planned for municipal water and sewer; the Region confirms the connection.'
                 if urban else 'Outside the urban area: a private well and septic system unless the Region says otherwise.'),
    } if official_plan else None
    seaton = any(str(h['attributes'].get('ZONING_AREA', '')).lower() == 'seaton' for h in zoning)
    garden_suite = additional_units(layers, parcel['_geom'] if parcel else None, primary_zone, rules, overlays, standards,
                                    servicing_status['in_urban_area'] if servicing_status else None)
    charges = dev_charges.for_lot(store_dir(), seaton, servicing_status['municipal_expected'] if servicing_status else None)

    property_id = None
    if parcel:
        a = parcel['attributes']
        property_id = {
            'address': _pick(a, r'addr|civic') or (addresses and _pick(addresses[0]['attributes'], r'addr|civic')),
            'roll_number': _pick(a, r'roll|arn'), 'pin': _pick(a, r'\bpin\b|^pin'),
            'legal_description': _legal_description(layers, parcel['_geom'], a),
            'area_m2': round(parcel['_geom'].area, 1), 'perimeter_m': round(parcel['_geom'].length, 1),
            'dimensions': dimensions,
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
        # The same short shape as the Toronto lookup, for the workspace's site step.
        'parcel': {k: v for k, v in {
            'address': (property_id or {}).get('address'),
            'zoning': ', '.join(zone_codes) or None,
            'by_law': ', '.join(bylaw_numbers) or None,
            'official_plan': ', '.join(filter(None, (_pick(h['attributes'], r'desig', r'land_?use', r'name')
                                                    for h in official_plan))) or None,
            'overlays': ', '.join(c.replace('_', ' ') for c in triggered) or None,
            'lot': f"{dimensions['width_m']} m × {dimensions['depth_m']} m" if dimensions else None,
            'setbacks': setback_summary(standards),
        }.items() if v},
        'source_url': zoning[0]['source_url'] if zoning else None,
        'additional_units': garden_suite,
        'permitted_uses': permitted_uses(primary_zone, rules),
        'servicing': servicing_status,
        'development_charges': charges,
        'buildable_area': mapping(_to_wgs84(envelope)) if envelope is not None else None,
        'source_label': 'City of Pickering zoning (stored on this server)',
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
                'lot_standards': standards,
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
                'council_amendments_naming_this_lot': lot_amendments(manifest, property_id, searched_codes),
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


_ALL_LOTS_LOCK = threading.Lock()
ALL_LOTS_COLUMNS = ['address', 'roll_number', 'pin', 'legal_description', 'zone_code', 'zone', 'exceptions',
                    'street_side', 'corner_lot', 'front_yard_m', 'rear_yard_m', 'interior_side_yard_m', 'other_side_yard_m',
                    'exterior_side_yard_m', 'lot_frontage_min_m', 'lot_area_min_m2', 'max_height', 'max_coverage_pct',
                    'lot_width_m', 'lot_depth_m', 'lot_area_m2', 'buildable_area_m2', 'complete', 'missing',
                    'lane_lot', 'attached_sides', 'basis', 'basis_note', 'basis_page', 'figure_setbacks', 'sources',
                    'latitude', 'longitude']


def _primary_zone(zoning_layers, geom):
    """The zone symbol covering most of a lot, read from whichever zoning layer covers it."""
    best, share = None, 0.0
    for layer in zoning_layers:
        for i in layer.tree.query(geom):
            attrs, zone_geom = layer.features[layer._indexed[int(i)]]
            overlap = zone_geom.intersection(geom).area if geom.area > 0 else float(zone_geom.contains(geom))
            code = _zone_code(attrs)
            if code and overlap > share:
                best, share = code, overlap
    return best


@lru_cache(maxsize=1)
def _all_lots(store: str, stamp: str) -> list[dict]:
    _, layers = load_store()
    rules = zone_rules()
    zoning_layers = [l for l in layers if l.meta['category'] == 'zoning' and l.tree is not None]
    rows = []
    fabric = _lot_fabric(layers)
    for layer in [fabric] if fabric else []:
        for attrs, geom in layer.features:
            if geom is None or geom.area <= 0:
                continue
            code = _primary_zone(zoning_layers, geom)
            lot, dims = _apply_rules(layers, geom, code, rules)
            std = lot['standards']
            # The by-law's figure, also where a common wall takes the side yard to nothing on that side.
            side = {v['applies']: v.get('stated', v['value']) for v in lot['setbacks_by_side'].values()}
            value = lambda key: (std.get(key) or {}).get('value')
            point = geom.representative_point()
            rows.append({
                'address': _pick(attrs, r'addr|civic'), 'roll_number': _pick(attrs, r'roll|arn'),
                'pin': _pick(attrs, r'\bpin\b|^pin'), 'legal_description': _legal_description(layers, geom, attrs),
                'zone_code': code, 'zone': lot['zone'], 'exceptions': ' '.join(lot['exceptions']),
                'street_side': lot['street_side'], 'corner_lot': lot['corner_lot'],
                'front_yard_m': side.get('front_yard'), 'rear_yard_m': side.get('rear_yard'),
                'interior_side_yard_m': value('interior_side_yard') if 'interior_side_yard' in side else None,
                'other_side_yard_m': (std.get('interior_side_yard') or {}).get('other_side'),
                'exterior_side_yard_m': side.get('exterior_side_yard') if lot['corner_lot'] else None,
                'lot_frontage_min_m': value('lot_frontage'), 'lot_area_min_m2': value('lot_area'),
                'max_height': value('building_height'), 'max_coverage_pct': value('lot_coverage'),
                'lot_width_m': (dims or {}).get('width_m'), 'lot_depth_m': (dims or {}).get('depth_m'),
                'lot_area_m2': round(geom.area, 1), 'buildable_area_m2': lot['buildable_area_m2'],
                'complete': lot['complete'], 'missing': ' '.join(lot['missing']),
                'lane_lot': lot['lane_lot'], 'attached_sides': ' '.join(lot['attached_sides']),
                'basis': lot['basis'], 'basis_note': lot['basis_note'], 'basis_page': lot['basis_page'],
                'figure_setbacks': ' | '.join(
                    f"{f['figure']}{' (' + f['applies_to'] + ')' if f.get('applies_to') else ''}: "
                    + '; '.join(f"{s['value_m']} m from {s['from']}" for s in f['setbacks'])
                    for f in lot['figure_setbacks'] if f['setbacks']),
                'sources': '; '.join(sorted({f"{v.get('from')} p.{v.get('page')}" for v in std.values()
                                             if v.get('from')})),
                'latitude': round(point.y / M_PER_DEG_LAT, 7), 'longitude': round(point.x / M_PER_DEG_LON, 7),
            })
    return rows


def all_lots() -> list[dict]:
    """Every stored parcel with its setbacks and standards from the by-law (cached per scrape)."""
    if load_store()[0] is None:
        return []
    root = store_dir()
    with _ALL_LOTS_LOCK:
        return _all_lots(str(root), str((root / 'manifest.json').stat().st_mtime_ns))


def setbacks_coverage() -> dict:
    """How many lots got every setback from the by-law, by zone, and what stopped the rest."""
    rows = all_lots()
    by_zone = {}
    for row in rows:
        entry = by_zone.setdefault(row['zone'] or 'no zone', {'lots': 0, 'complete': 0, 'missing': {}})
        entry['lots'] += 1
        entry['complete'] += bool(row['complete'])
        for key in (row['missing'] or '').split():
            entry['missing'][key] = entry['missing'].get(key, 0) + 1
    basis = {}
    for row in rows:
        basis[row['basis']] = basis.get(row['basis'], 0) + 1
    return {'lots': len(rows), 'complete': sum(1 for r in rows if r['complete']), 'by_basis': basis,
            'corner_lots': sum(1 for r in rows if r['corner_lot']),
            'without_zone': sum(1 for r in rows if not r['zone']),
            'without_street': sum(1 for r in rows if not r['street_side']),
            'by_zone': dict(sorted(by_zone.items(), key=lambda kv: -kv[1]['lots']))}


def warm():
    """Load the layers and the address index ahead of the first request; quiet if nothing is stored."""
    try:
        if load_store()[0] is not None:
            search_properties('warm')
            all_lots()
    except Exception:
        pass
