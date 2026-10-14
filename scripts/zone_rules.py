"""Read a zoning by-law's zone standards into structured rules, every number with its page.

Pickering's Zoning By-law 8149/24 sets each zone's lot and building requirements
in tables (minimum front yard, interior side yard, exterior side yard, rear yard,
frontage, lot area, maximum height and coverage), and site-specific exceptions in
numbered sections ("X 446", or "Exception Zone 12" in the older by-laws). This
module turns both into zone_rules.json, which the API applies lot by lot.

Tables are read with pdfplumber, in either orientation (zones across the top,
provisions down the side, or the reverse) and as single-zone tables whose zone is
named in the title. Exception sections are read line by line. Anything with a
number that could not be placed is listed under "unparsed", so a gap is visible.

    python scripts/zone_rules.py --store data/municipal/pickering   # rebuild from stored PDFs
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Provision keys, the words that name them, and whether the by-law states a floor or a ceiling.
PROVISIONS = [
    # First: the Seaton tables' "Min. Front Yard Landscaped Open Space" is a share of the yard, not a yard.
    ('landscaped_area', r'landscap', 'minimum'),
    ('exterior_side_yard', r'exterior\s+side\W{1,3}yard|flank(?:ag\s?e|ing)', 'minimum'),
    ('interior_side_yard', r'(interior\s+)?side\W{1,3}yard|interior\s+yard\s+width', 'minimum'),
    ('front_yard', r'front(?:age)?\s+yar[do]', 'minimum'),  # "FRONTAGE YARD DEPTH"; a scan's "FRONT YARO"
    ('rear_yard', r'rear\s*yard', 'minimum'),  # "REARYARD" in a scan
    ('lot_frontage', r'(lot\s+)?frontage', 'minimum'),
    ('lot_area', r'lot\s+area', 'minimum'),
    ('building_height', r'(building\s+)?height', 'maximum'),
    ('lot_coverage', r'(lot\s+)?coverage', 'maximum'),
    ('dwelling_depth', r'dwelling\s+depth|building\s+depth', 'maximum'),
    # The City Centre zones have no yards: a building stands 1.0 to 4.0 m from the street line.
    ('street_line_setback', r'building\s+setback\s+from\s+(?:the\s+)?street\s+line', 'minimum'),
    ('garage_projection', r'garage\s+projection|projection\s+of\s+(an?\s+)?(attached\s+)?garage', 'maximum'),
]
UNITS = {'m': 'm', 'metre': 'm', 'metres': 'm', 'meter': 'm', 'meters': 'm', 'm2': 'm2', 'm²': 'm2', 'sq m': 'm2',
         'square metres': 'm2', '%': '%', 'percent': '%', 'per cent': '%', 'storeys': 'storeys', 'storey': 'storeys',
         'ha': 'ha', 'hectares': 'ha'}
VALUE = re.compile(r'(\d+(?:[.,]\d+)?)\s*(square metres|sq\.? ?m|m2|m²|metres?|meters?|m\b|%|per ?cent|storeys?|ha\b|hectares)?',
                   re.I)
# Zone symbols: R4, R1A, RM2, C1, MU1, SLD2M, SA, A, OS-HL, (H)… but not ordinary words or units.
ZONE_TOKEN = r'[A-Z]{1,5}(?:[0-9]{1,2}[A-Z]{0,2})?(?:-[A-Z0-9]{1,3})?'
ZONE = re.compile(rf'^\(?{ZONE_TOKEN}\)?$')
NOT_ZONES = {'M', 'MIN', 'MAX', 'N/A', 'NA', 'TABLE', 'ZONE', 'ZONES', 'SEE', 'NOTE', 'AND', 'OR', 'THE', 'HA', 'A.',
             'FLOOR', 'LAND', 'OPEN', 'UNIT', 'AREA', 'LOT', 'USE', 'USES', 'SPACE', 'YARD', 'PART', 'MAP'}
# What may stand between a provision's name and its number: "DEPTH (minimum):", "width of", "shall be".
DIRECTLY_STATED = re.compile(r'(?:[\s:,()\-–·]|\b(?:side|yard|depth|wi\w{2,3}h|setback|minim(?:um|a)|maximum|min|max|per|dwelling|unit|of|shall|be|is|a)\b\.?)*\d',
                             re.I)
# A standard names a depth, a width or a minimum. "1) front yard: 0.6 metres" under "bay windows may
# encroach as follows" is how far a window may reach into the yard.
STATES_ITS_OWN = re.compile(r'\b(?:depth|wi\w{2,3}h|setback|minim(?:um|a)|maximum|min|max)\b', re.I)
NOT_A_STANDARD = re.compile(r'encroach|project|shall mean', re.I)
# What may come before a provision's name in its clause: an article, "minimum", a list mark.
OPENS_THE_CLAUSE = re.compile(r'''(?:[\s,()\-–"'“”‘’•.]|\b(?:the|a|an|minimum|maximum|min|max|required)\b'''
                              r'''|\(?\b(?:[ivxlc]{1,4}|\d{1,2}|[a-z])[.)])*''', re.I)
ABUTS_STREET = re.compile(r'abuts?\s+(?:a\s+)?street\D{0,40}?(\d+(?:\.\d+)?)\s*metres', re.I)
# A table's footnote: "The minimum interior side yard shall be 0.0 m where the common wall of a
# semi-detached dwelling abuts an interior side lot line being the adjoining wall of another..."
COMMON_WALL_NOTE = re.compile(r'[^.]*interior side yard shall be 0(?:\.0)?\s*m\s+where the common wall[^.]*\.', re.I)
# "1.2 metres one side, 0.6 metres other side", "0.3 of a metre one side, and 1.2 metres on the other
# side", "1.2 m on one side and 0.6 m on the other side"; and "One side 1.8 m and other side 3.0 m".
OTHER_MEASURE = re.compile(r'stepback|podium|tower|separation|balcon|amenity|active at grade|adjacent to|below grade|'
                           r'floor plate|continuous length|angular', re.I)
REFERENCE = re.compile(r'\b(?:schedule|figure|section|table|by-law|clause)s?\s+[\d.]+[\w()/-]*', re.I)
ONE_SIDE_AND_THE_OTHER = re.compile(r'(\d+(?:\.\d+)?)\s*(?:of a\s+)?(?:metres?|m)\b[^.;:]{0,25}?one side\W+(?:and\s+)?'
                                    r'(\d+(?:\.\d+)?)\s*(?:of a\s+)?(?:metres?|m)\b[^.;:]{0,25}?other side', re.I)
# Zone symbols the by-law misprints in a table: Table 14.25 has "SSWMP" for the SSWM zone it names above it.
ZONE_MISPRINTS = {'SSWMP': 'SSWM'}
# A height for every use a table's zones allow but the ones named before it (Section 14.8.2.2).
OTHER_USES_HEIGHT = re.compile(r'maximum height of all other uses shall be (\d+(?:\.\d+)?)\s*m\b', re.I)
# A Seaton table's "1.2 m & 0.6 m": the two interior side yards.
BOTH_SIDES = re.compile(r'(\d+(?:\.\d+)?)\s*m\s*&\s*(\d+(?:\.\d+)?)\s*m\b', re.I)
# A Seaton table's "6.0 m / 5.0 m adjacent to SNHS zone": a smaller figure where the lot abuts that zone.
NEXT_TO_ZONE = re.compile(r'/\s*(\d+(?:\.\d+)?)\s*m\s+adjacent\s+to\s+(?:an?\s+|the\s+)?([A-Z][A-Z0-9-]*)\s+zone', re.I)
ONE_SIDE_FIRST = re.compile(r'one side\s*(\d+(?:\.\d+)?)\s*(?:metres?|m)\b\W+(?:and\s+)?(?:the\s+)?other side\s*(\d+(?:\.\d+)?)', re.I)
LENGTH = re.compile(r'(\d+(?:\.\d+)?)\s*(?:metres?|metre s|meters?|m\b)', re.I)
SIDE_AND_FLANKAGE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:metres?|m)\s*(side|flankage)', re.I)
LABEL_ONLY = re.compile(r'(?:[\s:,()\-–·]|\b(?:side|yard|depth|wi\w{2,3}h|setback|minim(?:um|a)|maximum|min|max|per|dwelling|unit)\b\.?)*', re.I)
STATES_A_STANDARD = re.compile(r'yard|frontage|lot\s+area|flankag|setback\s+from\s+street\s+line', re.I)
# 'Zone Requirements ("S-SD-SA-3")': which of an exception's zones the standards below are for.
ZONE_HEADING = re.compile(r'Zone Requirements\s*\(\W*([A-Z][A-Z0-9/\-]*)')
LIST_MARK = re.compile('^[ (]*[0-9ivx]{1,3}[)] +')  # "1) " or "(ii) " opening a line, never the "1." of 1.2
# What a label may run on with before its value: "WIDTH FOR SINGLE DETACHED" (/ "DWELLINGS:" / value).
FOR_A_KIND = re.compile(r'[\s:,()\-–]*(?:width|depth)?\s*for\b', re.I)
# A line, or the start of one, that names a kind of dwelling: "semi-detached dwelling:", "for detached
# dwellings:", "multiple dwelling - horizontal:", "DWELLINGS:", "detached dwelling residential use:".
A_KIND = re.compile(r'\s*(?:for\s+)?(?:[A-Za-z][\w,/\-]*\s+){0,6}?(?:dwellings?|units?)\b[^:\d]{0,45}(?::\s*|\s*$|(?=\d))', re.I)
# A kind's name, as against a sentence that happens to mention dwellings.
KIND_NAME = re.compile(r'detached|attached|multiple|townhouse', re.I)
NOT_A_NAME = re.compile(r'\b(?:is|are|has|have|share|shall|where|which|that|those|such|on|may)\b', re.I)
# "> 4 ha: 15.0 < 4 ha: 12.0": one figure for lots over the size named, one for smaller lots.
BY_LOT_AREA = re.compile(r'>\s*(\d+(?:\.\d+)?)\s*ha\s*:\s*(\d+(?:\.\d+)?)\s*<\s*\1\s*ha\s*:\s*(\d+(?:\.\d+)?)', re.I)
BY_DWELLING = re.compile(r'\s*for\s+[\w\s,\-]*?dwellings?\s*:?\s*', re.I)
JOINED_KIND = re.compile('semi-? ?detached|attached|townhouse', re.I)
JOINED = re.compile(r'(?:[^.;\n]*\n)?[^.;\n]*(?:common wall|attached together|are attached|party wall)[^.;]*', re.I)
# "Buildings and structures shall be located entirely within the building envelope shown on Figure 1";
# "Setbacks from streets & property boundaries as per Figure 2".
# "The performance standards and provisions as set out on Figure 1 hereto shall apply".
DRAWN = re.compile(r'(?=[^.;]{0,260}\b(?:Figure|Schedule)\s*\d)(?=[^.;]{0,200}\b(?:envelope|build-to|setbacks?|yards?|performance standards)\b)'
                   r'\b(?:No building|Buildings?|Setbacks?|Front yards?|Building envelope|The performance standards)\b[^.;]{0,240}?'
                   r'\b(?:shown|illustrated|identified|as per|set out|indicated)\b[^.;]{0,60}?\b(?:Figure|Schedule)\s*\d+[^.;]{0,60}',
                   re.I)
ZONE_SECTION = re.compile(r'Zone Requirements\s*\(([^)]{1,160})\)')
ZONE_BREAK = re.compile(r'(?:Uses? Permitted|Provisions|Zone Requirements)\s*\(')
# 'on lands designated "S1" and "S2": 4.5 metres', 'on the lands designated "S2-13"' with its figure on
# the next line, 'on lands zoned "SA-12" 4.5 metres', 'B on lands designated "S3-2": 11 metres'.
QUOTED = r"""["“”'‘’]{1,2}\s*[A-Za-z][A-Za-z0-9/\-]*\s*["“”'‘’]{1,2}"""
DESIGNATED = re.compile(rf'\s*(?:[A-Z]\.?\s+)?(?:on|within) (?:the )?lands? (?:designated|zoned)\s+'
                        rf'(?:({QUOTED}(?:\s*(?:,|and|or|&)+\s*{QUOTED})*)(?:\s*zones?)?\s*(?::|(?=\s+\d)|\s*$)|(.+?):)', re.I)
# Under a label, the standard restated as a sentence: "the minimum rear yard depth for all lots shall
# be 7.5 metres", "...on either side, the minimum front yard depth shall be 4.5 metres".
SHALL_BE = re.compile(r'\s*(?:[^.;:\d]{0,40},\s*)?(?:the\s+)?(?:minimum|maximum)\b[^.;:\d]{0,60}?\bshall\s+be\s+', re.I)
# "for lots fronting on Fairport Road: 7.5 metres" / "for all other lots: 4.5 metres".
SOME_LOTS = re.compile(r'\s*(?:[A-Z]\.\s*)?(?:for|where)\b[^:]{3,90}:', re.I)
ALL_OTHER = re.compile(r'\s*(?:[A-Z]\.\s*)?for all other (?:lots|lands)\s*:?\s*', re.I)
# What a page carries at its head and foot, between a label and a figure split by the page break.
FURNITURE = re.compile(r'\s*(?:\d{1,4}|Section \d+ \|.*|Consolidated Zoning By-law.*|City of Pickering)\s*$')
# "SIDE YARD WIDTHS (minimal):" / "interior side yard: 1.5 metres" / "flankage side yard: 3 metres".
SIDE_WIDTHS = re.compile(r'\W*side yard widths?\s*\(minim\w*\)\s*:?\s*$', re.I)
EACH_SIDE = re.compile(r'\W*(interior|flankage|exterior)\s+side\s+yard\s*[:\-–]', re.I)
# A column heading in an exception's table of standards: '“S3-7” Zone', "SA-14 Zone".
ZONE_COLUMN = re.compile(r'\W*([A-Z][A-Z0-9]*(?:[-/][A-Z0-9]+)*)\W*\s*Zone\W*')
# A zone as an exception writes it, hyphens and all: S1-2, S-SD-SA, RH/MU, MD-H5.
DESIGNATION = re.compile(r'[A-Z][A-Z0-9]*(?:[-/][A-Z0-9]+)*')
EXCEPTION_HEADING = re.compile(r'^\s*(?:Exception(?:\s+Zone)?\s*(?:No\.?\s*)?|X\s?)(\d{1,4})\b(.*)$', re.I | re.M)


def provision_key(label: str):
    label = ' '.join(str(label or '').split())
    for key, pattern, bound in PROVISIONS:
        if re.search(pattern, label, re.I):
            stated = ('minimum' if re.search(r'\bmin', label, re.I) else
                      'maximum' if re.search(r'\bmax', label, re.I) else bound)
            return key, stated
    return None


def parse_value(cell):
    """First number in a cell with its unit, or None for blanks, dashes and "N/A"."""
    # Footnote markers are not values: "-(1)" is a dash and "4.5(1)" is 4.5.
    text = re.sub(r'\(\d+\)', '', ' '.join(str(cell or '').split())).strip()
    if not text or re.fullmatch(r'[-–—]|n/?a|not permitted|none', text, re.I):
        return None
    # "As shown on Schedule 5" and "see Section 4.23" name a place in the by-law, not an amount.
    text = REFERENCE.sub('', text)
    by_area = BY_LOT_AREA.search(text)
    if by_area:
        return {'value': float(by_area.group(2)), 'unit': None, 'raw': text,
                'small_lot': {'below_ha': float(by_area.group(1)), 'value': float(by_area.group(3))}}
    match = VALUE.search(text)
    if not match:
        return None
    unit = (match.group(2) or '').lower().replace('.', '')
    number = match.group(1)
    # "3,000" is three thousand; "7,5" is a decimal comma.
    number = number.replace(',', '' if re.fullmatch(r'\d{1,3},\d{3}', number) else '.')
    sides = ONE_SIDE_AND_THE_OTHER.search(text) or ONE_SIDE_FIRST.search(text) or BOTH_SIDES.search(text)
    both = {'other_side': float(sides.group(2))} if sides and sides.group(1) == number else {}
    near = NEXT_TO_ZONE.search(text)
    next_to = {'next_to': {'zone': near.group(2).upper(), 'value': float(near.group(1))}} if near else {}
    return {**both, **next_to, 'value': float(number), 'unit': UNITS.get(unit, unit or None), 'raw': text}


def _zone_cells(row):
    zones = []
    for cell in row:
        token = ' '.join(str(cell or '').split()).upper()
        family = re.fullmatch(r'([A-Z]{1,5}) ZONES', token)  # "CC Zones": one column for all of them
        zones.append(f'{family.group(1)}*' if family else
                     token if ZONE.match(token) and token.strip('()') not in NOT_ZONES else None)
    return zones


def _title_zones(text: str) -> list[str]:
    """Zones a page heading names: "Table 5: R4 Zone", "Lot and Building Requirements – RM1 and RM2 Zones"."""
    found = []
    for line in text.splitlines()[:12]:
        if re.search(r'zone|table|requirement', line, re.I):
            for token in re.findall(rf'\b{ZONE_TOKEN}\b', line):
                if token not in NOT_ZONES and token not in found and not token.isdigit():
                    found.append(token)
    return found


def rules_from_table(table, page_text: str, source: dict, carry: dict | None = None) -> tuple[dict, list]:
    """{zone: {provision: rule}} from one table, and the numeric rows it could not place.

    `carry` holds a table by building type open at the foot of the last page (its zones and the
    building type heading over its last rows), so its continuation without a title is still read.
    """
    rows = [list(r) for r in table if r and any(c not in (None, '') for c in r)]
    if len(rows) < 2:
        return {}, []
    out, unparsed = {}, []

    def put(zone, label, cell, note='', kind=None):
        key = provision_key(label)
        label = f'{label} {note}'
        value = parse_value(cell)
        rule = out.get(zone, {}).get(key[0]) if key else None
        if kind and rule is not None and rule.get('kind') and rule['bound'] == key[1]:
            # A later building type in a Seaton table: kept beside the first, and a dash is "none required".
            if rule['kind'] != kind and not any(k['kind'] == kind for k in rule.get('other_kinds', [])):
                stated = value or {'value': 0.0, 'unit': rule.get('unit'), 'raw': '-', 'none_required': True}
                rule.setdefault('other_kinds', []).append({**stated, 'kind': kind, 'bound': key[1],
                                                           'label': ' '.join(str(label).split()), **source})
            return
        if kind and key and rule is None and value is None and key[1] == dict((k, b) for k, _, b in PROVISIONS)[key[0]]:
            # The first building type's dash still answers for it: "none required", not "not read".
            value = {'value': 0.0, 'unit': None, 'raw': '-', 'none_required': True}
        if key and OTHER_MEASURE.search(' '.join(str(label).split())):
            key = None  # "Minimum Main Wall Stepback for Buildings greater than 37.5 m in Height"
        if key and key == ('street_line_setback', 'maximum'):
            key = ('street_line_setback_max', 'maximum')
        if key and value and key[0] == 'lot_area' and value['unit'] is None and re.search(r'\(ha\)', label, re.I):
            value['unit'] = 'ha'  # "Minimum Lot Area (ha) | 0.8"
        if key and value and key[0] == 'lot_frontage' and value['unit'] == '%':
            return  # "Active At Grade Frontages: 40% of the first storey" is not a lot's frontage
        if key and value:
            out.setdefault(zone, {}).setdefault(key[0], {**value, 'bound': key[1],
                                                         'label': ' '.join(str(label).split()), **source,
                                                         **({'kind': kind} if kind else {})})
        elif value and not key:
            unparsed.append({'zone': zone, 'label': ' '.join(str(label or '').split()), 'cell': value['raw'], **source})

    header = _zone_cells(rows[0])
    if sum(1 for z in header[1:] if z) >= 1 and not provision_key(rows[0][0] or ''):
        # Zones across the top, provisions down the first column.
        label = None
        for row in rows[1:]:
            # A requirement split over several rows by use keeps its label; the first case stated is kept.
            label = row[0] or label
            for zone, cell in zip(header[1:], row[1:]):
                if zone:
                    put(zone.strip('()'), label, cell)
        # A requirement the table reader lost the name of (the rural zones' rear yard, at the foot of
        # its page) is read from the page's text instead: "Minimum Rear Yard (m) - -" and under it
        # "Residential Uses 12.0 12.0", the first case stated.
        named = [z.strip('()') for z in header[1:] if z]
        lines = [' '.join(line.split()) for line in page_text.splitlines()]
        for i, line in enumerate(lines):
            key = provision_key(line)
            if (key and len(named) == len(header) - 1 and re.search(r'(?:\s[-–])+$', line)
                    and not any(key[0] in out.get(zone, {}) for zone in named)):
                for below in lines[i + 1:i + 3]:
                    cells = below.split()[-len(named):]
                    if len(cells) == len(named) and any(parse_value(c) for c in cells) and                             all(parse_value(c) or c in '-–' for c in cells):
                        for zone, cell in zip(named, cells):
                            put(zone, f"{line.rstrip('-– ')} – {' '.join(below.split()[:-len(named)])}", cell)
                        break
        return out, unparsed
    first_col = _zone_cells([r[0] for r in rows[1:]])
    if sum(1 for z in first_col if z) >= 1 and any(provision_key(c or '') for c in rows[0][1:]):
        # Zones down the side, provisions across the top.
        named = []
        for zone, row in zip(first_col, rows[1:]):
            if zone:
                zone = ZONE_MISPRINTS.get(zone.strip('()'), zone.strip('()'))
                named.append(zone)
                for label, cell in zip(rows[0][1:], row[1:]):
                    put(zone, label, cell)
                    key = provision_key(label)
                    # A dash for a minimum is "none required" (the SSWM and SNHS rows of Table 14.25 are all
                    # dashes); a dash for a maximum sets no maximum, so it is left out.
                    if key and key[1] == 'minimum' and parse_value(cell) is None and re.fullmatch(r'\s*[-–—]\s*', str(cell or '')):
                        out.setdefault(zone, {}).setdefault(key[0], {'value': 0.0, 'unit': None, 'raw': '-', 'none_required': True,
                                                                     'bound': 'minimum', 'label': ' '.join(str(label).split()), **source})
        # "The maximum height of all other uses shall be 12.5 m" under the table (Section 14.8.2.2).
        height = OTHER_USES_HEIGHT.search(' '.join(page_text.split()))
        for zone in named if height else ():
            out.setdefault(zone, {}).setdefault('building_height', {
                'value': float(height.group(1)), 'unit': 'm', 'raw': height.group(0), 'bound': 'maximum',
                'label': ' '.join(height.group(0).split()), **source})
        return out, unparsed
    zones = _title_zones(page_text)
    by_type = sum(1 for c in rows[0][1:] if provision_key(c or '')) >= 2
    continued = not zones and by_type and carry is not None and carry.get('zones') \
        and source.get('page', 0) - carry.get('page', -9) <= 1
    if continued:
        zones = carry['zones']
    if zones and by_type:
        # One zone's table by building type (the Seaton zones): provisions across the top, a row per
        # building type. The first building type listed is the standard as read, its name in the label,
        # and every other row is kept beside it for a lot of that type (lot_rules picks the row).
        group = carry.get('group', '') if continued else ''
        for row in rows[1:]:
            name = ' '.join(str(row[0] or '').split())
            if not any(parse_value(c) for c in row[1:]):
                # A heading names a dwelling or building; "private garage" alone is the tail of a row
                # split over a page break, and the heading over it still stands.
                if re.search(r'dwelling|building|home', name, re.I):
                    group = name
                continue
            # A row naming its own dwelling ("Duplex Dwelling") stands alone; "with attached private
            # garage" belongs to the dwelling heading over it. Footnote marks go: "lane(4)".
            own = re.search(r'dwelling', name, re.I) and not re.match(r'with\b', name, re.I)
            kind = ' '.join(re.sub(r'\(\d+\)', '', name if own else f'{group} {name}').split())
            for label, cell in zip(rows[0][1:], row[1:]):
                for zone in zones:
                    put(zone, label, cell, f'– {kind}', kind)
        if carry is not None:
            carry.update(zones=zones, group=group, page=source.get('page'))
        return out, unparsed
    if zones and sum(1 for r in rows if provision_key(r[0] or '')) >= 2:
        # One zone's table: provision | value (| more columns for the same zone's variants).
        for row in rows:
            for zone in zones:
                put(zone, row[0], next((c for c in row[1:] if parse_value(c)), None))
    return out, unparsed


def unmerged(table) -> list[list]:
    """A found table's text, with a merged cell's text repeated in every position the cell spans.

    The PDF reader puts a merged cell's text in its first position and None in the rest, which is how a
    yard shared by four zones, or a standard shared by two kinds of lot, reads as missing. A cell that
    is simply empty comes back as '' and stays empty.
    """
    rows = table.extract()
    # The reader lays cells out by their left and top edges, so those edges number the columns and rows.
    lefts, tops = sorted({cell[0] for cell in table.cells}), sorted({cell[1] for cell in table.cells})
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if cell is None and r < len(tops) and c < len(lefts):
                x, y = lefts[c] + 0.5, tops[r] + 0.5
                span = next((b for b in table.cells if b[0] <= x < b[2] and b[1] <= y < b[3]), None)
                if span:
                    row[c] = rows[tops.index(span[1])][lefts.index(span[0])]
    return rows


def rules_by_zone_row(table, source: dict) -> dict:
    """{zone: {provision: rule}} from a table with a row per zone and the zone's symbol in a column of
    its own, as the older exception zones set out their standards ("Figure 1").

    Such a table has a heading two rows deep ("Minimum Yards" over "Front", "Side and Flankage",
    "Rear") and yards merged down the column for several zones; unmerged() has put each merged
    cell's text in every row it covers.
    """
    rows = [[' '.join(str(c or '').split()) for c in r] for r in table if r and any(r)]
    width = max(map(len, rows), default=0)
    rows = [r + [''] * (width - len(r)) for r in rows]
    symbol = lambda cell: bool(ZONE.match(cell)) and cell.strip('()') not in NOT_ZONES  # as written: "S1", not "Front"
    counts = [sum(symbol(r[c]) for r in rows) for c in range(width)]
    column = max(range(width), key=counts.__getitem__, default=None)
    first = next((i for i, r in enumerate(rows) if column is not None and symbol(r[column])), 0)
    if column is None or counts[column] < 2 or first == 0:
        return {}
    labels = []
    for c in range(width):
        parts = []
        for depth, row in enumerate(rows[:first]):
            cell, left = row[c], c
            # A heading spanning several columns sits in the first of them; the rest read as blank.
            while not cell and depth < first - 1 and left > 0 and rows[first - 1][c]:
                left -= 1
                cell = row[left]
            parts.append(cell)
        label = ' '.join(p for p in parts if p)
        if len(parts) > 1 and re.search(r'\byards?\b', parts[0], re.I) and not re.search(r'yard', parts[-1], re.I):
            label = f'{parts[0]}: {parts[-1]} yard'  # "Minimum Yards: Front yard"
        labels.append(label)
    out = {}
    for row in rows[first:]:
        if not symbol(row[column]):
            continue
        rules = out.setdefault(row[column].strip('()'), {})
        joined = next((cell for cell in row[:column] if JOINED_KIND.search(cell)), None)
        for c, (label, cell) in enumerate(zip(labels, row)):
            if c == column or not cell:
                continue
            if re.search(r'side.*flankage', label, re.I):
                # One cell for both: "1.2 metres side 2.7 metres flankage", or just "1.2 metres 2.7
                # metres" in the heading's order. Anything else is left unread.
                lengths = LENGTH.findall(cell)
                pairs = [(n, w.lower()) for n, w in SIDE_AND_FLANKAGE.findall(cell)] or \
                    (list(zip(lengths, ('side', 'flankage'))) if len(lengths) == 2 else [])
                for number, which in pairs:
                    key = 'interior_side_yard' if which == 'side' else 'exterior_side_yard'
                    rules.setdefault(key, {'value': float(number), 'unit': 'm', 'raw': cell, 'bound': 'minimum',
                                           'label': label, **source})
                continue
            key, value = provision_key(label), parse_value(cell)
            if key and value and (key[0].endswith('yard') or key[0] == 'lot_frontage'):
                # "1 dwelling per registered lot 15 metres": the length, not the count before it.
                length = LENGTH.search(cell)
                value = {**value, 'value': float(length.group(1)), 'unit': 'm'} if length else None
            if key and value:
                rules.setdefault(key[0], {**value, 'bound': key[1], 'label': label, **source})
            on_street = ABUTS_STREET.search(cell) if key and key[0] == 'interior_side_yard' else None
            if on_street:  # "1.2 metres unless side yard abuts street then minimum shall be 2.7 metres"
                rules.setdefault('exterior_side_yard', {'value': float(on_street.group(1)), 'unit': 'm', 'raw': cell,
                                                        'bound': 'minimum', 'label': label, **source})
        if joined and 'interior_side_yard' in rules:
            # The row is for "Semi-detached Dwellings" or "Single Attached Dwellings", which meet their
            # neighbour at the side lot line: the side yard is the open side's.
            rules['interior_side_yard'].setdefault('common_wall', f'The by-law gives this side yard for "{joined}", '
                                                                  'which are joined at the side lot line.')
    return {zone: rules for zone, rules in out.items() if rules}


def rules_by_lot_type(table, source: dict, carried: list | None = None) -> tuple[list, list]:
    """([{type, provisions}], column headings) from a newer exception's table: a column per kind of lot
    ("9.0 m single dwelling", "semi-detached dwelling"), a row per standard.

    The table runs on to the next page without its headings, so that part is read with the headings
    carried from the page before; its first row is then the tail of a cell split by the page break.
    """
    rows = [[' '.join(str(c or '').split()) for c in r] for r in table if r and any(r)]
    width = max(map(len, rows), default=0)
    rows = [r + [''] * (width - len(r)) for r in rows]
    counts = [sum(bool(provision_key(r[c])) for r in rows) for c in range(width)]
    label = max(range(width), key=counts.__getitem__, default=0)
    if len(rows) < 2 or counts[label] < 2 or width - label < 3:
        return [], []
    head = rows[0][label + 1:]
    if not rows[0][label] and sum('dwelling' in c.lower() for c in head) >= 2:
        types, body = head, rows[1:]
    elif carried and len(carried) == width - label - 1:
        types, body = carried, rows
    else:
        return [], []
    kinds = [{'type': kind, 'provisions': {}} for kind in types]
    for row in body:
        key = provision_key(row[label])
        if not key or re.search(r'accessory', row[label], re.I):  # "Lot Coverage of All Accessory Buildings"
            continue
        for kind, cell in zip(kinds, row[label + 1:]):
            value = parse_value(cell)
            if value and (key[0].endswith('yard') or key[0] == 'lot_frontage'):
                length = LENGTH.search(cell)
                value = {**value, 'value': float(length.group(1)), 'unit': 'm'} if length else None
            if value and key[0] == 'interior_side_yard' and re.search(r'common wall', cell, re.I):
                value['common_wall'] = cell  # "...share a common wall, no interior side yard shall be required"
            if value:
                kind['provisions'].setdefault(key[0], {**value, 'bound': key[1], 'label': row[label], **source})
    return kinds, types


def rules_by_zone_column(table, source: dict) -> dict:
    """{zone: {provision: rule}} from an exception's table with a column per zone ('“S3-7” Zone') and a
    lettered row per standard: "(c)" | "Front Yard Depth (minimum)" | "7.5 metres" | "4.5 metres"."""
    rows = [[' '.join(str(c or '').split()) for c in r] for r in table if r and any(r)]
    heads = [ZONE_COLUMN.fullmatch(c) for c in rows[0]] if len(rows) > 1 else []
    out = {}
    for row in rows[1:] if any(heads) else ():
        label = next((c for c, head in zip(row, heads) if not head and provision_key(c)), None)
        key = provision_key(label) if label and not re.search('accessory', label, re.I) else None
        for head, cell in zip(heads, row) if key else ():
            value = parse_value(cell) if head else None
            if value and (key[0].endswith('yard') or key[0] == 'lot_frontage'):
                length = LENGTH.search(cell)  # "i) 7.5 metres ii) 6.0 metres for the lands in the hatched area"
                value = {**value, 'value': float(length.group(1)), 'unit': 'm'} if length else None
            if value and key[0] == 'interior_side_yard' and re.search(r'common wall', cell, re.I):
                value['common_wall'] = cell
            if value:
                out.setdefault(head.group(1), {}).setdefault(key[0], {**value, 'bound': key[1], 'label': label, **source})
    return out


def _open_sections(pages: list[str]) -> list:
    """For each page, the (exception, zone) whose requirements are open at the top of it."""
    opened, code, zone = [], None, None
    for text in pages:
        opened.append((code, zone))
        marks = [(m.start(), 'X', m) for m in EXCEPTION_HEADING.finditer(text)] +                 [(m.start(), 'Z', m) for m in ZONE_HEADING.finditer(text)]
        for _, kind, mark in sorted(marks, key=lambda m: m[0]):
            code, zone = (f'X{int(mark.group(1))}', None) if kind == 'X' else (code, mark.group(1))
    return opened


def rules_from_text(text: str, source: dict) -> dict:
    """Provisions stated in prose: "the minimum rear yard shall be 7.5 metres".

    The number has to follow the provision's name directly ("REAR YARD DEPTH (minimum): 7.5 metres").
    A sentence that only mentions a yard ("erected in the rear yard and not less than 1.0 metres
    from...") or defines one is not that yard's standard, and a missing standard is reported as
    missing rather than guessed.
    """
    rules = {}
    text = re.sub(r'(?<=\d)\.\s(?=\d\s*(?:m\b|metres?))', '.', text)  # scanned by-laws: "2. 7 metres"
    text = re.sub(r'(?<=\d)\s\.(?=\d\s*(?:m\b|metres?))', '.', text)  # and "1 .2 metres"
    text = re.sub(r'(?i)\b(side)\.(\s+yard)', r'\1\2', text)  # and "INTERIOR SIDE. YARD WIDTH"
    lines, leads, previous = [], [], ''
    for row in text.split('\n'):
        # A row that carries on the sentence above it is judged with that row's words in front of it.
        carries_on = row.lstrip()[:1].islower() and previous.strip()[-1:] not in ('', '.', ':', ';')
        clauses = re.split(r';|(?<=\.)\s+(?=[A-Z(])', row)
        lines += clauses
        leads += [previous if carries_on else ''] + [''] * (len(clauses) - 1)
        previous = row
    for i, line in enumerate(lines):
        if SIDE_WIDTHS.match(line):  # one heading for both side yards, each named on a line under it
            both = {}
            for below in lines[i + 1:i + 14]:
                side = EACH_SIDE.match(below)
                value = parse_value(below[side.end():]) if side else None
                if (_is_a_label(below) and not side) or NOT_A_STANDARD.search(below):
                    break
                if value:
                    both.setdefault('interior_side_yard' if side.group(1).lower() == 'interior' else 'exterior_side_yard',
                                    {**value, 'bound': 'minimum', 'label': ' '.join(f'{line} {below}'.split())[:200], **source})
            for side, rule in both.items():
                rules.setdefault(side, rule)
            if both:
                continue
        key = provision_key(line)
        if not key or not STATES_ITS_OWN.search(line) or NOT_A_STANDARD.search(line):
            continue
        before, *_, after = re.split(PROVISIONS[[p[0] for p in PROVISIONS].index(key[0])][1], line, maxsplit=1,
                                     flags=re.I)
        # The standard opens its clause and is written as a heading: "REAR YARD DEPTH (minimum): 7.5
        # metres", "Minimum rear yard 7.5 metres". Mid-sentence ("units attached above grade may have a
        # minimum side yard width of 0.0 metres") or as a lower-case list item ("minimum rear yard depth
        # of 0.6 metres" under "Detached Garage Requirements:") it is some other clause's special case.
        opening = re.split(r'[:;]', f'{leads[i]} {before}')[-1]
        first = re.search(r'[A-Za-z]', opening + line[len(before):])
        if not OPENS_THE_CLAUSE.fullmatch(opening) or not (first and first.group().isupper()):
            continue
        named, others, where, said = None, [], i, ''
        if not DIRECTLY_STATED.match(after):
            # The value is on a line below the label, under a line or two saying what it is for:
            #   "INTERIOR SIDE YARD WIDTH:" / "minimum 1.2 metres each side"
            #   "FRONT YARD DEPTH (minimum):" / 'on lands designated "S1" and "S2": 4.5 metres'
            #   "SIDE YARD WIDTH (minimum):" / 'on the lands designated "S3":' / "1) minimum 1.2 metres each side"
            #   "INTERIOR SIDE YARD WIDTH FOR SINGLE DETACHED" / "DWELLINGS:" / "minimum 1.2 metres one side"
            #   "FRONT YARD DEPTH (minimum):" / "semi-detached dwelling: 4.5 metres"
            # A yard given zone by zone is kept for the zones named, each with its own figure; one given
            # by kind of dwelling is read for the first kind, which stays in the label.
            below = _value_below(lines, i + 1) if LABEL_ONLY.fullmatch(after) or FOR_A_KIND.match(after) else None
            if not below:
                continue
            said, after, named, at = below
            where = at
            while named:  # the other zones' figures, down to the next standard
                more = _value_below(lines, at + 1, only_named=True)
                if not more:
                    break
                theirs, rest, zones, at = more
                if parse_value(rest):
                    others.append({**parse_value(rest), 'bound': key[1], 'applies_to': zones,
                                   'label': ' '.join(f'{line} {theirs}'.split())[:200], **source})
            line = f'{line} {said}'
        if not DIRECTLY_STATED.match(after):
            continue
        if (re.search('one side', after, re.I) and not re.search('other', after, re.I) and where + 1 < len(lines)
                and re.search('other', lines[where + 1], re.I)):
            # "0.3 metres one side" / "2) 1.2 metres other side"; "1.2 metres one side, no" / "minimum the other"
            after = _no_minimum(f"{after} {LIST_MARK.sub('', lines[where + 1])}")
        # From the figure itself: a scan's "WI0TH (minimum): 2.7 metres" has a digit in its label.
        after = _no_minimum(after)
        value = parse_value(after[DIRECTLY_STATED.match(after).end() - 1:])
        if value and value['value'] > 60 and value['unit'] != 'm':
            continue  # a page or section number, not a yard: "FRONT YARD DEPTH (minimum): 164"
        total = re.search(r'aggregate[^.;]{0,80}?(\d+(?:\.\d+)?)\s*metres', ' '.join(lines[where:where + 3]), re.I)
        if value and value.get('other_side') == 0.0 and total:
            # "1.2 metres one side, no minimum the other provided that the aggregate of actual side yard
            # widths on the lot equal or exceed 1.8 metres": the other side is what makes up the total.
            value['other_side'] = round(max(float(total.group(1)) - value['value'], 0.0), 2)
        if value and key[0] not in rules:
            rules[key[0]] = {**value, 'bound': key[1], 'label': ' '.join(line.split())[:200], **source}
            if named:
                rules[key[0]]['applies_to'] = named
            if ALL_OTHER.search(said):
                rules[key[0]]['varies'] = ' '.join(said.split())[:300]
            named_kind = lambda m: bool(m) and bool(KIND_NAME.search(m.group(0))) and not NOT_A_NAME.search(m.group(0))
            name = lambda m: re.sub(r'(?i)^for\s+|\s+minimum$', '', ' '.join(m.group(0).split()).strip(' :'))
            kind = next((m for m in map(A_KIND.match, lines[i + 1:where + 1]) if named_kind(m)), None)
            if kind:
                # A figure for each kind of dwelling: the first is the standard as read, and the others
                # are kept beside it for a lot of that kind.
                rules[key[0]]['kind'] = name(kind)
                for n in range(where + 1, min(where + 40, len(lines))):
                    other = A_KIND.match(lines[n])
                    if _is_a_label(lines[n]):
                        break
                    if not named_kind(other):
                        continue
                    rest = lines[n][other.end():]
                    if not rest.strip() and other.group(0).rstrip().endswith(':') and n + 1 < len(lines):
                        rest = LIST_MARK.sub('', lines[n + 1])
                    elif re.search('one side', rest, re.I) and not re.search('other', rest, re.I) and n + 1 < len(lines):
                        rest = f'{rest} {lines[n + 1]}'
                    stated = DIRECTLY_STATED.match(_no_minimum(rest))
                    theirs = parse_value(_no_minimum(rest)[stated.end() - 1:]) if stated else None
                    if theirs:
                        rules[key[0]].setdefault('other_kinds', []).append(
                            {**theirs, 'kind': name(other), 'bound': key[1],
                             'label': ' '.join(f'{lines[i]} {lines[n]}'.split())[:200], **source})
            if others:
                rules[key[0]]['other_zones'] = others
    return rules


def _no_minimum(text: str) -> str:
    """"no minimum one side, minimum 1.2 metres other side" and "1.2 metres one side, no minimum the
    other", with the side that needs no yard written as 0 metres."""
    text = re.sub(r'no minimum (?:on )?one side,?\s*(?:and\s+)?(?:minimum\s+)?(\d+(?:\.\d+)?)\s*metres?\s+(?:on\s+)?(?:the\s+)?other side',
                  r'\1 metres one side, 0 metres other side', text, flags=re.I)
    return re.sub(r'one side,?\s*(?:and\s+)?no\s+minimum\s+(?:on\s+)?(?:the\s+)?other(?:\s+side)?', 'one side, 0 metres other side',
                  text, flags=re.I)


def _is_a_label(line: str) -> bool:
    """A line that opens a standard of its own: "FLANKAGE SIDE YARD WIDTH (minimum): 2.7 metres"."""
    key = provision_key(line)
    if not key or not STATES_ITS_OWN.search(line) or NOT_A_STANDARD.search(line):
        return False
    before = re.split(PROVISIONS[[p[0] for p in PROVISIONS].index(key[0])][1], line, maxsplit=1, flags=re.I)[0]
    return bool(OPENS_THE_CLAUSE.fullmatch(re.split(r'[:;]', before)[-1])) and line.lstrip()[:1].isupper()


def _value_below(lines: list, start: int, only_named: bool = False):
    """(what the lines say, the text that opens with the value, zones named or None, line index).

    From `start`, reads past the lines that only say what a value is for, to the value. With
    only_named it looks further, as far as the next standard, for the next 'on lands designated' line.
    """
    said, zones = [], None
    for at in range(start, min(start + (40 if only_named else 5), len(lines))):
        line = lines[at]
        designated = DESIGNATED.match(line)
        if not line.strip() or (only_named and not designated and not said and not _is_a_label(line)):
            continue
        if _is_a_label(line):
            return None
        rest = LIST_MARK.sub('', line)
        if designated:
            zones, rest = zones_named(designated.group(1) or designated.group(2)), LIST_MARK.sub('', line[designated.end():])
        else:
            kind = A_KIND.match(line) or SHALL_BE.match(line)
            rest = LIST_MARK.sub('', line[kind.end():]) if kind else rest
            # Where some lots are set apart, the figure for all the other lots is the standard, and
            # the label keeps the lots it sets apart.
            other = next((n for n in range(at + 1, min(at + 5, len(lines))) if ALL_OTHER.match(lines[n])), None)
            if not kind and SOME_LOTS.match(line) and other is not None:
                return (' '.join([*said, *lines[at:other + 1]]), lines[other][ALL_OTHER.match(lines[other]).end():],
                        zones, other)
        said.append(line)
        rest = _no_minimum(rest)
        if DIRECTLY_STATED.match(rest):
            return ' '.join(said), rest, zones, at
        if any(ch.isdigit() for ch in rest):
            if not only_named:
                return None  # some other sentence
            said, zones = [], None  # a zone's figure that is not a width ("north side yard 1.2 metres"): on to the next zone
    return None


def zones_named(text: str) -> list[str]:
    """The zones in '"S1", "S1-2" and "S-SD-SA" Zones', whole: S1, S1-2, S-SD-SA."""
    return [zone for zone in DESIGNATION.findall(text.upper()) if zone not in ('AND', 'OR', 'ZONE', 'ZONES')]


def _for_zone(rule: dict, zone: str) -> dict | None:
    """The reading of a standard that is for this zone, where a standard is given zone by zone."""
    for reading in [rule, *rule.get('other_zones', [])]:
        if not reading.get('applies_to') or zone in reading['applies_to']:
            return {k: v for k, v in reading.items() if k != 'other_zones'}
    return None


def exceptions_from_pages(pages: list[str], source: dict) -> dict:
    """{"X12": {"heading", "page", "provisions", "text"}} from exception sections."""
    text, offsets = '', []
    for number, page in enumerate(pages, 1):
        offsets.append((len(text), number))
        text += page + '\n'
    page_at = lambda pos: max(n for start, n in offsets if start <= pos)
    heads = list(EXCEPTION_HEADING.finditer(text))
    found = {}
    for i, head in enumerate(heads):
        body = text[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        code = f'X{int(head.group(1))}'
        page = page_at(head.start())
        entry = found.setdefault(code, {'heading': ' '.join(head.group(0).split())[:160], 'page': page,
                                        'provisions': {}, 'text': ' '.join(body.split())[:4000], **source})
        # Read page by page, so each standard cites the page it is on rather than the section's first.
        def read(begin, end):
            for (start, number), (stop, _) in zip(offsets, offsets[1:] + [(len(text), None)]):
                if max(start, begin) < min(stop, end):
                    chunk = text[max(start, begin):min(stop, end)]
                    kept = [line for line in chunk.split('\n') if line.strip() and not FURNITURE.match(line)]
                    if kept and (kept[-1].rstrip().endswith(':') or DESIGNATED.match(kept[-1])) and stop < end:
                        # A standard named at the foot of a page has its figure at the top of the next,
                        # and a list of figures zone by zone carries on there.
                        over = [line for line in text[stop:min(stop + 500, end)].split('\n')
                                if line.strip() and not FURNITURE.match(line)][:4]
                        chunk = '\n'.join(kept + over[:next((n for n, line in enumerate(over) if _is_a_label(line)), 4)])
                    yield from rules_from_text(chunk, {**source, 'page': number}).items()

        def at_a_common_wall(span: str, side_yard: dict | None):
            # "...where dwellings on abutting lots share a common wall, no interior side yard shall be
            # required adjacent to that wall": kept with the side yard it qualifies.
            said = next((' '.join(m.group(0).split()) for m in JOINED.finditer(span)
                         if re.search(r'side yard|side lot line|no minimum|not required', m.group(0), re.I)), None)
            if said and side_yard is not None:
                side_yard.setdefault('common_wall', said[:300])

        def drawn(begin, end):
            # Where the by-law gives a zone's setbacks on a drawing: what it says, and the page.
            for (start, number), (stop, _) in zip(offsets, offsets[1:] + [(len(text), None)]):
                if max(start, begin) < min(stop, end):
                    said = DRAWN.search(' '.join(text[max(start, begin):min(stop, end)].split()))
                    if said:
                        return {'text': said.group(0).strip()[:300], 'page': number, **source}
            return None

        for key, rule in read(head.end(), head.end() + len(body)):
            entry['provisions'].setdefault(key, rule)
        at_a_common_wall(body, entry['provisions'].get('interior_side_yard'))
        if drawn(head.end(), head.end() + len(body)):
            entry.setdefault('by_figure', {})['*'] = drawn(head.end(), head.end() + len(body))
        # An exception often covers several zones, each under its own 'Zone Requirements ("S-SD" Zone)'
        # heading, running to the next zone's "Uses Permitted". Each zone keeps its own standards.
        breaks = sorted(m.start() for m in ZONE_BREAK.finditer(body))
        for section in ZONE_SECTION.finditer(body):
            end = next((b for b in breaks if b > section.end()), len(body))
            zones = zones_named(section.group(1))
            entry.setdefault('zone_sections', []).extend(z for z in zones if z not in entry.get('zone_sections', []))
            for key, rule in read(head.end() + section.end(), head.end() + end):
                for zone in zones:
                    mine = _for_zone(rule, zone)
                    if mine:
                        entry.setdefault('by_zone', {}).setdefault(zone, {}).setdefault(key, mine)
            for zone in zones:
                at_a_common_wall(body[section.end():end], entry.get('by_zone', {}).get(zone, {}).get('interior_side_yard'))
                if drawn(head.end() + section.end(), head.end() + end):
                    entry.setdefault('by_figure', {})[zone] = drawn(head.end() + section.end(), head.end() + end)
    return found


def extract(documents: list[dict], store: Path) -> dict:
    """zone_rules.json content from the stored zoning by-law documents."""
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None
    zones, exceptions, unparsed, read, established = {}, {}, [], [], set()
    # The consolidated by-law is read first, so its tables win over an older by-law naming the same zone.
    for doc in sorted(documents, key=lambda d: '8149' not in str(d.get('title'))):
        label = f"{doc.get('title', '')} {doc.get('url', '')}"
        if doc.get('kind') != 'pdf' or not re.search(r'zoning|by-?law|exception|8149', label, re.I):
            continue
        path = store / doc['file']
        pages = json.loads((store / doc['text_file']).read_text(encoding='utf-8')) if doc.get('text_file') else []
        source = {'document': doc.get('title'), 'file': doc['file'], 'url': doc.get('url')}
        read.append(doc['file'])
        opened, tabled, typed, running = _open_sections(pages), {}, {}, None
        if '8149' in str(doc.get('title')):
            # The zones the by-law establishes, from its Table 2.1 and the page after it.
            at = next((i for i, page in enumerate(pages) if 'Establishment of Zones' in page and 'Zoning Symbol' in page), None)
            for page in pages[at:at + 3] if at is not None else ():
                established |= {z for z in re.findall(rf'\b{ZONE_TOKEN}\b', page) if z not in NOT_ZONES and len(z) > 1}
        if pdfplumber and path.exists():
            try:
                with pdfplumber.open(path) as pdf:
                    carry = {}  # a table by building type running over a page break
                    for number, page in enumerate(pdf.pages, 1):
                        stored = pages[number - 1] if number <= len(pages) else None
                        # Tables are read only where a page states a yard or lot standard. A zoning
                        # schedule is a map, and searching its line work for tables takes gigabytes.
                        if stored is not None and not STATES_A_STANDARD.search(stored):
                            continue
                        page_text = page.extract_text() or stored or ''
                        tables = page.find_tables()
                        heads = page.search(r'Exception\s+Zone\s+(\d{1,4})', regex=True) if tables else []
                        zoned = page.search(ZONE_HEADING.pattern, regex=True) if tables else []
                        for table in tables:
                            cells, where = unmerged(table), {**source, 'page': number}
                            found, missed = rules_from_table(cells, page_text, where, carry)
                            unparsed += missed
                            for zone, rules in found.items():
                                for key, rule in rules.items():
                                    kept = zones.setdefault(zone, {}).setdefault(key, rule)
                                    if kept is not rule and kept.get('kind') and rule.get('kind') and kept['bound'] == rule['bound']:
                                        # A table by building type continued over a page break: its
                                        # later rows join the rows read on the page before.
                                        have = {kept['kind'], *(k['kind'] for k in kept.get('other_kinds', []))}
                                        for row in [rule, *rule.get('other_kinds', [])]:
                                            if row['kind'] not in have:
                                                kept.setdefault('other_kinds', []).append(
                                                    {k: v for k, v in row.items() if k != 'other_kinds'})
                                                have.add(row['kind'])
                            # A table of zones by row belongs to the exception it sits in: the last
                            # heading above it on the page, or the section open at the top of the page.
                            code, named = opened[number - 1] if number <= len(opened) else (None, None)
                            marks = [(h['top'], 'X', h) for h in heads] + [(h['top'], 'Z', h) for h in zoned]
                            for top, kind, mark in sorted(marks, key=lambda m: m[0]):
                                if top < table.bbox[1]:
                                    code, named = ((f"X{int(mark['groups'][0])}", None) if kind == 'X'
                                                   else (code, mark['groups'][0]))
                            by_zone = {**rules_by_zone_row(cells, where), **rules_by_zone_column(cells, where)} if code else {}
                            for zone, rules in by_zone.items():
                                for key, rule in rules.items():
                                    tabled.setdefault(code, {}).setdefault(zone, {}).setdefault(key, rule)
                            # A table by kind of lot belongs to the zone whose requirements it sits
                            # under, and carries on over the page break without its headings.
                            carries = running and running[:2] == (code, named) and number - running[2] <= 1
                            kinds, types = rules_by_lot_type(cells, where, running[3] if carries else None)                                 if code and named else ([], [])
                            if kinds:
                                kept = typed.setdefault(code, {}).setdefault(named, kinds)
                                for mine, theirs in zip(kept, kinds):
                                    for key, rule in theirs['provisions'].items():
                                        mine['provisions'].setdefault(key, rule)
                                running = (code, named, number, types)
                        # A footnote under a zone table, on its page or the one after: "The minimum
                        # interior side yard shall be 0.0 m where the common wall of a semi-detached..."
                        note = COMMON_WALL_NOTE.search(' '.join(page_text.split()))
                        for rules in zones.values() if note else ():
                            rule = rules.get('interior_side_yard') or {}
                            if rule.get('file') == doc['file'] and rule.get('page') in (number, number - 1):
                                rule['common_wall'] = note.group(0).strip()
                        page.flush_cache()
            except Exception as exc:
                unparsed.append({'file': doc['file'], 'error': repr(exc)})
        for code, entry in exceptions_from_pages(pages, source).items():
            current = exceptions.setdefault(code, entry)
            if current is not entry:  # an amendment restating an exception: later documents add provisions
                current.setdefault('also_in', []).append(entry['file'])
                for key, rule in entry['provisions'].items():
                    current['provisions'].setdefault(key, rule)
        for code, by_zone in tabled.items():
            for zone, rules in by_zone.items() if code in exceptions else ():
                # The exception's table of zones by row is its most specific word, over its prose.
                exceptions[code].setdefault('by_zone', {}).setdefault(zone, {}).update(rules)
        for code, by_type in typed.items():
            if code in exceptions:
                exceptions[code].setdefault('by_lot_type', {}).update(by_type)
    families = {family: sorted(z for z in established if z.startswith(family[:-1]) and z != family[:-1])
                for family in zones if family.endswith('*')}
    return {'zones': zones, 'exceptions': exceptions, 'families': families, 'unparsed': unparsed[:500], 'documents_read': read,
            'table_reader': 'pdfplumber' if pdfplumber else None}


def build(store: Path) -> dict:
    """Rebuild zone_rules.json for the stored snapshot and point the manifest at it."""
    manifest_path = store / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    rules = extract(manifest['documents'], store)
    file = str(Path(manifest.get('snapshot', '.')) / 'zone_rules.json')
    (store / file).write_text(json.dumps(rules, indent=1), encoding='utf-8')
    manifest['zone_rules_file'] = file
    tmp = manifest_path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    tmp.replace(manifest_path)
    return rules


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--store', type=Path, default=Path(__file__).resolve().parent.parent / 'data' / 'municipal' / 'pickering')
    args = parser.parse_args()
    result = build(args.store)
    print(json.dumps({'zones': len(result['zones']), 'exceptions': len(result['exceptions']),
                      'unparsed': len(result['unparsed']), 'table_reader': result['table_reader']}, indent=1))
    sys.exit(0 if result['zones'] else 2)
