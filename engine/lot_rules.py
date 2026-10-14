"""Apply a zoning by-law's standards to one lot: its setbacks, side by side, and where each came from.

The rules come from zone_rules.json (scripts/zone_rules.py reads them out of the
by-law). For a lot this module takes the zone covering most of it, starts from
that zone's table, lets the lot's exception sections override it, works out
which side faces the street (and, on a corner lot, which side flanks the second
street, where the exterior side yard applies), checks the lot's own frontage and
area, and draws the area left to build on inside the setbacks.

Geometry is in local metres (see engine.pickering_zoning). Nothing here is
interpreted beyond what a table or exception states; a standard the by-law text
did not yield is reported as missing, never filled with a default.
"""
import math
import re

import shapely
import shapely.ops
from shapely import affinity
from shapely.geometry import box

LANE_KIND = re.compile(r'lane|garage at the rear', re.I)
SETBACKS = ('front_yard', 'rear_yard', 'interior_side_yard', 'exterior_side_yard')
LOT_STANDARDS = ('lot_frontage', 'lot_area', 'lot_coverage', 'building_height', 'landscaped_area')
OPPOSITE = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
# Roads this close to the lot boundary count as fronting it.
FRONTING_M = 15.0


def split_zone(code: str) -> tuple[str, list[str]]:
    """("R4", ["X12"]) from "R4-X12", "R4 (X12)" or "R4(H) X 12"."""
    base = re.split(r'[-(/\s]', code.strip())[0].upper()
    exceptions = [f'X{int(n)}' for n in re.findall(r'\bX\s?(\d+)\b', code.upper().replace('-', ' '))]
    return base, exceptions


def _side_of(centre, geom, rotation_deg: float = 0.0) -> str:
    """Which side of the lot a road is on, in the lot's own frame: the lot turned upright by its
    rotation, as _envelope draws it. Judged by compass instead, a lot at an angle to north got its
    front yard on a side lot line."""
    target = shapely.ops.nearest_points(centre, geom)[1]
    dx, dy = target.x - centre.x, target.y - centre.y
    turn = math.radians(rotation_deg)
    dx, dy = dx * math.cos(turn) + dy * math.sin(turn), dy * math.cos(turn) - dx * math.sin(turn)
    return ('E' if dx > 0 else 'W') if abs(dx) > abs(dy) else ('N' if dy > 0 else 'S')


def street_sides(parcel, roads: list, rotation_deg: float = 0.0) -> list[str]:
    """Sides of the lot with a road within FRONTING_M of its boundary, nearest road first."""
    centre = parcel.centroid
    near = sorted((g for g in roads if g.distance(parcel) <= FRONTING_M), key=lambda g: g.distance(parcel))
    sides = []
    for road in near:
        side = _side_of(centre, road, rotation_deg)
        if side not in sides:
            sides.append(side)
    return sides


def resolve(code: str | None, rules: dict, frontage_m: float | None = None, lane_lot: bool = False) -> dict:
    """Each standard for a zone code: the zone table's value, replaced by any exception's."""
    if not code:
        return {}
    base, exceptions = split_zone(code)
    # The zone as the exception names it: "S-SD-SA-3" for a lot mapped "S-SD-SA-3-X332".
    designation = re.sub(r'[-\s(]*X\s?\d+\)?', '', code.upper()).strip('- ')
    resolved = {}
    for key, rule in (rules.get('zones', {}).get(base) or {}).items():
        resolved[key] = {**rule, 'from': f'Zone {base} table'}
    for exception in exceptions:
        section = rules.get('exceptions', {}).get(exception) or {}
        # The exception's own table of zones by row, where it has one, is its most specific word.
        by_zone = section.get('by_zone') or {}
        # Where the exception sets its zones out one by one, a lot takes its own zone's standards and
        # not the first zone's; the exception's standards as a whole are for an exception with one set.
        sectioned = {designation, base} & set(section.get('zone_sections') or ())
        general = {} if sectioned else section.get('provisions') or {}
        stated = [(key, rule, f'Exception {exception}') for key, rule in
                  [*general.items(), *(by_zone.get(designation) or by_zone.get(base) or {}).items()]]
        # A newer exception gives one zone a column per kind of lot ("9.0 m single dwelling", "12.0 m
        # single dwelling", "semi-detached dwelling"). The lot takes the widest kind its own frontage
        # reaches, measured with half a metre's grace, and the column is named beside each value.
        kinds = [k for k in (section.get('by_lot_type') or {}).get(designation, []) if 'lot_frontage' in k['provisions']]
        # Kinds reached from a rear lane ("Lane single attached dwelling", "Integrated garage at the
        # rear") are for lots with a lane behind them, and the others for lots without.
        by_lane = [k for k in kinds if bool(LANE_KIND.search(k['type'])) == lane_lot]
        kinds = by_lane or kinds
        fits = [k for k in kinds if frontage_m is not None and k['provisions']['lot_frontage']['value'] <= frontage_m + 0.5]
        if fits:
            kind = max(fits, key=lambda k: k['provisions']['lot_frontage']['value'])
            stated += [(key, rule, f'Exception {exception}, "{kind["type"]}" column') for key, rule in kind['provisions'].items()]
        for key, rule, said_by in stated:
            # 'on lands designated "S1" and "S2": 4.5 metres' is not this lot's standard in an S4 zone.
            if rule.get('applies_to') and not {base, designation} & set(rule['applies_to']):
                continue
            resolved[key] = {**rule, 'from': said_by, 'overrides': resolved.get(key, {}).get('value')}
    return resolved


def _envelope(parcel, rotation_deg: float, sides: dict):
    """The parcel inset by each side's setback, in the lot's own frame, as a polygon (or None)."""
    centre = parcel.centroid
    upright = affinity.rotate(parcel, -rotation_deg, origin=centre)
    minx, miny, maxx, maxy = upright.bounds
    inner = box(minx + sides['W'], miny + sides['S'], maxx - sides['E'], maxy - sides['N'])
    if inner.is_empty or inner.area <= 0 or minx + sides['W'] >= maxx - sides['E'] or miny + sides['S'] >= maxy - sides['N']:
        return None
    return affinity.rotate(upright.intersection(inner), rotation_deg, origin=centre)


def attached_sides(parcel, rotation_deg: float, footprints: list) -> list[str]:
    """Sides of the lot, in its own frame, where its building carries on across the lot line: the
    common wall of a semi-detached or townhouse dwelling.

    The building has to stand just beyond the line along it, not merely touch it: the City's footprints
    and its parcel fabric sit up to a metre apart, so a detached house can appear to touch its lot line.
    """
    centre = parcel.centroid
    minx, miny, maxx, maxy = affinity.rotate(parcel, -rotation_deg, origin=centre).bounds
    beyond = {'W': box(minx - 2.5, miny, minx - 0.5, maxy), 'E': box(maxx + 0.5, miny, maxx + 2.5, maxy),
              'S': box(minx, miny - 2.5, maxx, miny - 0.5), 'N': box(minx, maxy + 0.5, maxx, maxy + 2.5)}
    sides = set()
    for footprint in footprints:
        if footprint.intersection(parcel).area >= 10:
            upright = affinity.rotate(footprint, -rotation_deg, origin=centre)
            sides |= {side for side, strip in beyond.items() if upright.intersection(strip).area >= 2}
    return sorted(sides)


def apply_to_lot(parcel, code: str | None, rules: dict, roads: list, dimensions: dict | None,
                 lanes: list | None = None, attached: list | None = None) -> dict:
    """The lot's setbacks by side, the lot standards, checks of the lot itself, and the buildable area.

    `lanes` are the centrelines of rear lanes, kept apart from `roads`: a lot fronts on its street,
    and a lane behind it marks a lane-based lot. `attached` is attached_sides() for the lot.
    """
    base, exceptions = split_zone(code) if code else (None, [])
    rotation = (dimensions or {}).get('rotation_deg', 0.0)
    streets = street_sides(parcel, roads, rotation) if parcel is not None else []
    behind = [s for s in street_sides(parcel, lanes, rotation) if s not in streets] if parcel is not None and lanes else []
    if not streets:  # its only road is a street that happens to be called a lane
        streets, behind = behind, []
    street = streets[0] if streets else (dimensions or {}).get('street_side')
    # A corner lot has a second street on a side next to (not opposite) the front. A side where the
    # dwelling is joined to its neighbour is not on a street, whatever road passes near it.
    flank = next((s for s in streets[1:] if s not in (street, OPPOSITE.get(street), *(attached or ()))), None)
    if flank and dimensions:
        # By-law 8149/24, "Lot Line, Front": where more than one lot line is on a street, the shorter
        # one is the front. The nearest road is not always that one.
        on_street = lambda side: dimensions['width_m' if side in 'NS' else 'depth_m']
        if on_street(flank) < on_street(street):
            street, flank = flank, street
    through = bool(street and OPPOSITE[street] in streets)
    lane_lot = bool(street and OPPOSITE[street] in behind)
    frontage = dimensions['width_m' if street in 'NS' else 'depth_m'] if dimensions and street else None
    standards = resolve(code, rules, frontage, lane_lot)

    by_side, missing = {}, []
    if street:
        rear = OPPOSITE[street]
        for side in 'NESW':
            key = ('front_yard' if side == street else 'rear_yard' if side == rear else
                   'exterior_side_yard' if side == flank else 'interior_side_yard')
            # Without an exterior side yard in the by-law, the flank falls back to the interior one, said so.
            rule = standards.get(key) or (standards.get('interior_side_yard') if key == 'exterior_side_yard' else None)
            by_side[side] = {'applies': key, **({k: rule[k] for k in ('value', 'unit', 'from', 'document', 'file', 'page', 'label')
                                                 if k in rule} if rule else {'value': None})}
            if rule and key == 'exterior_side_yard' and 'exterior_side_yard' not in standards:
                by_side[side]['note'] = 'No exterior side yard stated; the interior side yard is shown.'
            if rule and key == 'interior_side_yard' and rule.get('common_wall') and side in (attached or ()):
                # The by-law asks for no side yard along a common wall, and the City's building
                # footprint shows this dwelling joined to its neighbour on this side.
                by_side[side].update(value=0.0, stated=rule['value'],
                                     note=f"Joined to the neighbouring dwelling on this side. {rule['common_wall']}")
    # "1.2 metres one side, 0.6 metres other side": the by-law does not say which side is which, so the
    # first open side takes the first figure and the second the other. The width left to build on is the
    # same either way; only where it sits across the lot is not known.
    both = (standards.get('interior_side_yard') or {}).get('other_side')
    open_sides = [s for s in 'NESW' if by_side.get(s, {}).get('applies') == 'interior_side_yard' and 'stated' not in by_side[s]]
    if both is not None and len(open_sides) == 2:
        by_side[open_sides[1]].update(value=both, note='The by-law gives a different width for each side yard and does not '
                                                       'say which side is which.')
    for key in SETBACKS + LOT_STANDARDS:
        if key not in standards and not (key == 'exterior_side_yard' and not flank):
            missing.append(key)

    checks = []
    if dimensions and street:
        frontage = dimensions['width_m'] if street in 'NS' else dimensions['depth_m']
        rule = standards.get('lot_frontage')
        if rule and rule.get('unit') in ('m', None):
            checks.append({'standard': 'lot_frontage', 'required': rule['value'], 'lot': round(frontage, 1),
                           'ok': frontage >= rule['value'] - 0.05, 'from': rule['from'], 'page': rule.get('page')})
    rule = standards.get('lot_area')
    if rule and parcel is not None:
        required = rule['value'] * (10_000 if rule.get('unit') == 'ha' else 1)
        checks.append({'standard': 'lot_area', 'required': required, 'lot': round(parcel.area, 1),
                       'ok': parcel.area >= required - 0.5, 'from': rule['from'], 'page': rule.get('page')})

    envelope = None
    if parcel is not None and dimensions and by_side and all(
            by_side[s]['value'] is not None and by_side[s].get('unit') in ('m', None) for s in 'NESW'):
        envelope = _envelope(parcel, dimensions['rotation_deg'], {s: by_side[s]['value'] for s in 'NESW'})

    coverage = standards.get('lot_coverage')
    return {
        'zone': base, 'zone_code': code, 'exceptions': exceptions,
        'exceptions_without_text': [x for x in exceptions if x not in rules.get('exceptions', {})],
        'street_side': street, 'flank_side': flank, 'corner_lot': bool(flank), 'through_lot': through,
        'lane_lot': lane_lot, 'attached_sides': list(attached or ()),
        'setbacks_by_side': by_side,
        'standards': {k: {kk: v.get(kk) for kk in ('value', 'unit', 'bound', 'from', 'document', 'page', 'label',
                                                   'overrides', 'file', 'other_side')}
                      for k, v in standards.items()},
        'missing': missing, 'lot_checks': checks,
        'buildable_area_m2': round(envelope.area, 1) if envelope is not None else None,
        'max_coverage_m2': round(parcel.area * coverage['value'] / 100, 1)
        if coverage and coverage.get('unit') == '%' and parcel is not None else None,
        '_envelope': envelope,
        'complete': bool(by_side) and all(v['value'] is not None for v in by_side.values()),
        'approximate': bool(dimensions and dimensions.get('rectangularity', 1) < 0.9),
    }
