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

LANE_KIND = re.compile(r'\blane\b|garage at the rear', re.I)
# Kinds of dwelling that meet a neighbour at the side lot line ("detached" does not contain "attached").
JOINED_KIND = re.compile(r'semi|\battached|multiple|townhouse|horizontal', re.I)
SETBACKS = ('front_yard', 'rear_yard', 'interior_side_yard', 'exterior_side_yard')
LOT_STANDARDS = ('lot_frontage', 'lot_area', 'lot_coverage', 'building_height', 'landscaped_area')
OPPOSITE = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
# What the by-law says of a standard a Seaton zone's table has no column for.
NOT_IN_TABLE = {
    'lot_coverage': "The zone's table sets no lot coverage. Where an additional dwelling unit is in an accessory "
                    'building, all buildings on the lot may cover at most 45% of it (By-law 8149/24, Section 14.2.9.1, p. 161).',
}
# Zones whose standards are their neighbours': By-law 8149/24, Section 14.9.2.1.
TAKES_ADJACENT = {'SUT': 'Section 14.9.2.1: the most restrictive provisions of any zone adjacent to the SUT zone'}
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


def _zone_table(base: str, designation: str, rules: dict) -> tuple[str, dict]:
    """(zone, its table): the zone's own table, or the one the by-law gives a whole family of zones
    ("CC Zones") where it lists this zone in that family. The map writes CC2 as "CC 2" and CCR1 as
    "CC Res 1"."""
    zones, families = rules.get('zones', {}), rules.get('families') or {}
    spelled = designation.replace(' ', '')
    for zone in dict.fromkeys((base, spelled, spelled.replace('RES', 'R'))):
        if zones.get(zone):
            return zone, zones[zone]
        family = next((f for f, members in families.items() if zone in members), None)
        if family and zones.get(family):
            return zone, zones[family]
    # By-law 8149/24, Table 13.3, note 1: "Detached dwellings and agricultural buildings and structures
    # in the UR zone shall be subject to the applicable requirements of the Agriculture zone."
    if base == 'UR' and zones.get('A'):
        return 'A (which Table 13.3, note 1 applies to the UR zone)', zones['A']
    return base, {}


def drawn_rule(code: str | None, rules: dict) -> dict | None:
    """Where the by-law gives a lot's setbacks on a drawing ("within the building envelope shown on
    Figure 1"): what it says and the page, for the lot's own zone in its exception."""
    if not code:
        return None
    base, exceptions = split_zone(code)
    designation = re.sub(r'[-\s(]*X\s?\d+\)?', '', code.upper()).strip('- ')
    for exception in exceptions:
        section = rules.get('exceptions', {}).get(exception) or {}
        drawn = section.get('by_figure') or {}
        sectioned = {designation, base} & set(section.get('zone_sections') or ())
        found = drawn.get(designation) or drawn.get(base) or (None if sectioned else drawn.get('*'))
        if found:
            return {**found, 'exception': exception}
    return None


def figure_setbacks(exceptions: list[str], rules: dict) -> list[dict]:
    """The setbacks each of the lot's exceptions draws on a figure instead of stating, as read off the
    drawing by eye (data/pickering_figure_setbacks.json), each from a named street or lot line, in metres."""
    figures = []
    for exception in exceptions:
        for figure in (rules.get('exceptions', {}).get(exception) or {}).get('figures', []):
            per_unit = 0.3048 if figure['unit'] == 'ft' else 1.0
            figures.append({'exception': exception, **{k: figure.get(k) for k in ('figure', 'document', 'page', 'applies_to', 'note')},
                            'setbacks': [{'from': line, 'value_m': round(value * per_unit, 1),
                                          'stated': f"{value:g} {figure['unit']}"} for line, value in figure['setbacks']]})
    return figures


def _for_kind(rule: dict, joined: bool) -> dict:
    """Where the by-law gives a standard for each kind of dwelling ("for detached dwellings", "for
    semi-detached dwellings"), the figure for the lot's own kind: joined to its neighbour, or not."""
    mine = next((k for k in [rule, *rule.get('other_kinds', [])]
                 if k.get('kind') and bool(JOINED_KIND.search(k['kind'])) == joined), rule)
    if mine is rule:
        return rule
    kept = {k: rule[k] for k in ('common_wall', 'overrides') if k in rule}
    return {**kept, **mine, 'from': f"{rule['from']}, for \"{mine['kind']}\""}


def _most_restrictive(tables: list[dict], said: str) -> dict:
    """Each standard at its most restrictive across the given zones' standards: the largest minimum and
    the smallest maximum, in the same unit; a dash ("none required") restricts nothing."""
    found = {}
    for table in tables:
        for key, rule in table.items():
            if rule.get('value') is None or rule.get('none_required'):
                continue
            have = found.get(key)
            if have is not None and have.get('unit') != rule.get('unit'):
                continue
            tighter = have is None or (rule['value'] < have['value'] if rule.get('bound') == 'maximum'
                                       else rule['value'] > have['value'])
            if tighter:
                found[key] = {**rule, 'from': f"{rule.get('from')}, by {said}"}
    return found


def _dwelling(kind: str) -> str:
    """The kind of dwelling a Seaton row names, without its garage: "Detached Dwelling … with attached
    private garage" is a detached dwelling."""
    return re.split(r'\s+with\s+', kind, maxsplit=1)[0]


def _table_row(table: dict, frontage_m: float | None, lane_lot: bool, joined: bool) -> str | None:
    """The row of a zone table set out by building type (the Seaton zones) that fits this lot: its kind of
    dwelling (joined to a neighbour or not), whether it is reached from a rear lane, and the first row
    listed whose minimum frontage the lot reaches, with half a metre's grace. None for other tables."""
    source = table.get('lot_frontage') if (table.get('lot_frontage') or {}).get('other_kinds') else \
        next((r for r in table.values() if r.get('other_kinds')), None)
    rows = [r for r in [source or {}, *(source or {}).get('other_kinds', [])] if r.get('kind')]
    if len(rows) < 2:
        return None
    rows = [r for r in rows if bool(JOINED_KIND.search(_dwelling(r['kind']))) == joined] or rows
    rows = [r for r in rows if bool(LANE_KIND.search(r['kind'])) == lane_lot] or rows
    if source is not table.get('lot_frontage') or frontage_m is None:
        return rows[0]['kind']
    fits = [r for r in rows if r['value'] <= frontage_m + 0.5]
    return (fits[0] if fits else min(rows, key=lambda r: r['value']))['kind']


def _in_row(rule: dict, row: str | None) -> dict:
    """A standard as its table sets it for the lot's row; the rule as read where the table has no rows."""
    if row is None:
        return rule
    mine = next((k for k in [rule, *rule.get('other_kinds', [])] if k.get('kind') == row), rule)
    kept = {k: rule[k] for k in ('common_wall',) if k in rule}
    return {**kept, **{k: v for k, v in mine.items() if k != 'other_kinds'}}


def resolve(code: str | None, rules: dict, frontage_m: float | None = None, lane_lot: bool = False,
            joined: bool = False) -> dict:
    """Each standard for a zone code: the zone table's value, replaced by any exception's."""
    if not code:
        return {}
    base, exceptions = split_zone(code)
    # The zone as the exception names it: "S-SD-SA-3" for a lot mapped "S-SD-SA-3-X332".
    designation = re.sub(r'[-\s(]*X\s?\d+\)?', '', code.upper()).strip('- ')
    resolved = {}
    zone, table = _zone_table(base, designation, rules)
    row = _table_row(table, frontage_m, lane_lot, joined)
    for key, rule in table.items():
        resolved[key] = {**_in_row(rule, row), 'from': f'Zone {zone} table' + (f', "{row}" row' if row else ''),
                         **({'row': row} if row else {})}
    for exception in exceptions:
        section = rules.get('exceptions', {}).get(exception) or {}
        # The exception's own table of zones by row, where it has one, is its most specific word.
        by_zone = section.get('by_zone') or {}
        # Where the exception sets its zones out one by one, a lot takes its own zone's standards and
        # not the first zone's; the exception's standards as a whole are for an exception with one set.
        sectioned = {designation, base} & set(section.get('zone_sections') or ())
        general = {} if sectioned else section.get('provisions') or {}
        # A figure that is a table of yards by zone (read from the drawing; see figure_setbacks) gives
        # the yards the text leaves to it, and anything the text states still has the last word.
        drawn = [(key, {'value': value, 'unit': 'm', 'document': figure['document'], 'page': figure['page']},
                  f"Exception {exception}, {figure['figure']}")
                 for figure in section.get('figures', [])
                 for key, value in ((figure.get('yards') or {}).get(designation) or
                                    (figure.get('yards') or {}).get(base) or {}).items()]
        stated = drawn + [(key, rule, f'Exception {exception}') for key, rule in
                          [*general.items(), *(by_zone.get(designation) or by_zone.get(base) or {}).items()]]
        # A newer exception gives one zone a column per kind of lot ("9.0 m single dwelling", "12.0 m
        # single dwelling", "semi-detached dwelling"). The lot takes the widest kind its own frontage
        # reaches, measured with half a metre's grace, and the column is named beside each value.
        kinds = [k for k in (section.get('by_lot_type') or {}).get(designation, []) if 'lot_frontage' in k['provisions']]
        # Kinds reached from a rear lane ("Lane single attached dwelling", "Integrated garage at the
        # rear") are for lots with a lane behind them, and the others for lots without.
        by_lane = [k for k in kinds if bool(LANE_KIND.search(k['type'])) == lane_lot]
        fit = lambda some: [k for k in some if frontage_m is not None and k['provisions']['lot_frontage']['value'] <= frontage_m + 0.5]
        # A lot too narrow for any column of its own sort takes the widest it reaches of the others.
        fits = fit(by_lane) or fit(kinds)
        if fits:
            kind = max(fits, key=lambda k: k['provisions']['lot_frontage']['value'])
            stated += [(key, rule, f'Exception {exception}, "{kind["type"]}" column') for key, rule in kind['provisions'].items()]
        for key, rule, said_by in stated:
            # 'on lands designated "S1" and "S2": 4.5 metres' is not this lot's standard in an S4 zone.
            if rule.get('applies_to') and not {base, designation} & set(rule['applies_to']):
                continue
            resolved[key] = {**rule, 'from': said_by, 'overrides': resolved.get(key, {}).get('value')}
    return {key: _for_kind(rule, joined) for key, rule in resolved.items()}


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
                 lanes: list | None = None, attached: list | None = None, neighbours: dict | None = None) -> dict:
    """The lot's setbacks by side, the lot standards, checks of the lot itself, and the buildable area.

    `lanes` are the centrelines of rear lanes, kept apart from `roads`: a lot fronts on its street,
    and a lane behind it marks a lane-based lot. `attached` is attached_sides() for the lot.
    `neighbours` are the zones the lot abuts, {zone: [their shapes]}, for a yard set apart beside one.
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
    standards = resolve(code, rules, frontage, lane_lot, joined=bool(attached))
    if base in TAKES_ADJACENT and not standards and neighbours:
        standards = _most_restrictive([resolve(zone, rules) for zone in neighbours if zone != base], TAKES_ADJACENT[base])
    # "> 4 ha: 15.0 / < 4 ha: 12.0" (the ORMA zone): a lot under the size named takes the second figure.
    for key, rule in standards.items():
        small = rule.get('small_lot')
        if small and parcel is not None and parcel.area < small['below_ha'] * 10_000:
            standards[key] = {**rule, 'value': small['value']}
    # A zone regulated by a setback from the street line (the City Centre zones) has no yards: its
    # street sides take that setback, and the by-law asks nothing of the other sides.
    street_line = standards.get('street_line_setback') if 'front_yard' not in standards else None

    by_side, missing = {}, []
    if street:
        rear = OPPOSITE[street]
        for side in 'NESW':
            key = ('front_yard' if side == street else 'rear_yard' if side == rear else
                   'exterior_side_yard' if side == flank else 'interior_side_yard')
            # Without an exterior side yard in the by-law, the flank falls back to the interior one, said so.
            rule = standards.get(key) or (standards.get('interior_side_yard') if key == 'exterior_side_yard' else None)
            unasked = bool(street_line) and rule is None and key in ('rear_yard', 'interior_side_yard')
            if street_line and rule is None:
                rule = {**street_line, 'value': 0.0} if unasked else street_line
            by_side[side] = {'applies': key, **({k: rule[k] for k in ('value', 'unit', 'from', 'document', 'file', 'page', 'label')
                                                 if k in rule} if rule else {'value': None})}
            if rule and key == 'exterior_side_yard' and 'exterior_side_yard' not in standards and not street_line:
                by_side[side]['note'] = 'No exterior side yard stated; the interior side yard is shown.'
            if rule and rule.get('varies'):
                by_side[side]['note'] = f"The by-law sets some lots apart from this figure: {rule['varies']}"
            if unasked:
                by_side[side]['note'] = ("The zone's table sets a setback from the street line and no side or rear yard; "
                                         'its building separation and height rules apply instead.')
            if rule and rule.get('none_required'):
                by_side[side]['note'] = "The zone's table sets no minimum for this kind of lot (a dash in the table)."
            # "6.0 m / 5.0 m adjacent to SNHS zone": the smaller figure on a side where the lot abuts that zone.
            near = (rule or {}).get('next_to')
            if near and parcel is not None and side in {_side_of(parcel.centroid, g, rotation)
                                                        for g in (neighbours or {}).get(near['zone'], [])}:
                by_side[side].update(value=near['value'],
                                     note=f"Abuts the {near['zone']} zone on this side: {rule.get('raw', '')}.")
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
    # A table set out by building type (the Seaton zones) has a column for each standard it sets; one it
    # has no column for is not regulated by the zone, which is not the same as not found.
    by_type = any(rule.get('row') for rule in standards.values())
    not_regulated = {key: NOT_IN_TABLE.get(key, "The zone's table sets no such standard.")
                     for key in LOT_STANDARDS if by_type and key not in standards}
    for key in SETBACKS + LOT_STANDARDS:
        if key not in standards and key not in not_regulated and not (key == 'exterior_side_yard' and not flank)                 and not (street_line and key in SETBACKS):
            missing.append(key)
    # What the lot's setbacks rest on, so a lot without yards still says why and where to look.
    complete = bool(by_side) and all(v['value'] is not None for v in by_side.values())
    drawn = None if complete else drawn_rule(code, rules)
    basis = ('street_line' if street_line and complete else 'yards' if complete else 'figure' if drawn else
             'no_zone' if not code else 'no_street' if not street else
             'partial' if any(k in standards for k in SETBACKS) else 'none_stated')
    notes = {
        'street_line': "The zone's table sets a setback from the street line and no side or rear yard.",
        'figure': (drawn or {}).get('text'),
        'no_zone': "No zoning polygon covers this lot in the City's zoning layer.",
        'no_street': 'No street centreline lies within 15 m of this lot, so its front could not be placed.',
        'partial': 'The by-law text gives some of this lot\'s yards; the others are listed as missing.',
        'none_stated': 'The by-law states no yards for this zone in words or in a table that could be read.',
    }

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
        'basis': basis, 'basis_note': notes.get(basis), 'basis_page': (drawn or street_line or {}).get('page') if basis in ('figure', 'street_line') else None,
        'basis_document': (drawn or street_line or {}).get('document') if basis in ('figure', 'street_line') else None,
        'figure_setbacks': figure_setbacks(exceptions, rules) if basis == 'figure' else [],
        'setbacks_by_side': by_side,
        'standards': {k: {kk: v.get(kk) for kk in ('value', 'unit', 'bound', 'from', 'document', 'page', 'label',
                                                   'overrides', 'file', 'other_side')}
                      for k, v in standards.items()},
        'missing': missing, 'not_regulated': not_regulated, 'lot_checks': checks,
        'buildable_area_m2': round(envelope.area, 1) if envelope is not None else None,
        'max_coverage_m2': round(parcel.area * coverage['value'] / 100, 1)
        if coverage and coverage.get('unit') == '%' and parcel is not None else None,
        '_envelope': envelope,
        'complete': complete,
        'approximate': bool(dimensions and dimensions.get('rectangularity', 1) < 0.9),
    }
