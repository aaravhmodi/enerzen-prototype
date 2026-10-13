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
    ('exterior_side_yard', r'exterior\s+side\s+yard|flank(?:ag\s?e|ing)', 'minimum'),
    ('interior_side_yard', r'(interior\s+)?side\s+yard', 'minimum'),
    ('front_yard', r'front\s+yard', 'minimum'),
    ('rear_yard', r'rear\s+yard', 'minimum'),
    ('lot_frontage', r'(lot\s+)?frontage', 'minimum'),
    ('lot_area', r'lot\s+area', 'minimum'),
    ('building_height', r'(building\s+)?height', 'maximum'),
    ('lot_coverage', r'(lot\s+)?coverage', 'maximum'),
    ('landscaped_area', r'landscap', 'minimum'),
    ('dwelling_depth', r'dwelling\s+depth|building\s+depth', 'maximum'),
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
DIRECTLY_STATED = re.compile(r'(?:[\s:,()\-–]|\b(?:side|yard|depth|width|setback|minimum|maximum|min|max|of|shall|be|is|a)\b\.?)*\d',
                             re.I)
# A standard names a depth, a width or a minimum. "1) front yard: 0.6 metres" under "bay windows may
# encroach as follows" is how far a window may reach into the yard.
STATES_ITS_OWN = re.compile(r'\b(?:depth|width|setback|minimum|maximum|min|max)\b', re.I)
NOT_A_STANDARD = re.compile(r'encroach|project|shall mean', re.I)
# What may come before a provision's name in its clause: an article, "minimum", a list mark.
OPENS_THE_CLAUSE = re.compile(r'''(?:[\s,()\-–"'“”‘’•.]|\b(?:the|a|an|minimum|maximum|min|max|required)\b'''
                              r'''|\(?\b(?:[ivxlc]{1,4}|\d{1,2}|[a-z])[.)])*''', re.I)
LENGTH = re.compile(r'(\d+(?:\.\d+)?)\s*(?:metres?|metre s|meters?|m\b)', re.I)
SIDE_AND_FLANKAGE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:metres?|m)\s*(side|flankage)', re.I)
LABEL_ONLY = re.compile(r'(?:[\s:,()\-–]|\b(?:side|yard|depth|width|setback|minimum|maximum|min|max)\b\.?)*', re.I)
STATES_A_STANDARD = re.compile(r'yard|frontage|lot\s+area|flankag', re.I)
# 'Zone Requirements ("S-SD-SA-3")': which of an exception's zones the standards below are for.
ZONE_HEADING = re.compile(r'Zone Requirements\s*\(\W*([A-Z][A-Z0-9/\-]*)')
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
    match = VALUE.search(text)
    if not match:
        return None
    unit = (match.group(2) or '').lower().replace('.', '')
    number = match.group(1)
    # "3,000" is three thousand; "7,5" is a decimal comma.
    number = number.replace(',', '' if re.fullmatch(r'\d{1,3},\d{3}', number) else '.')
    return {'value': float(number), 'unit': UNITS.get(unit, unit or None), 'raw': text}


def _zone_cells(row):
    zones = []
    for cell in row:
        token = ' '.join(str(cell or '').split()).upper()
        zones.append(token if ZONE.match(token) and token.strip('()') not in NOT_ZONES else None)
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


def rules_from_table(table, page_text: str, source: dict) -> tuple[dict, list]:
    """{zone: {provision: rule}} from one table, and the numeric rows it could not place."""
    rows = [list(r) for r in table if r and any(c not in (None, '') for c in r)]
    if len(rows) < 2:
        return {}, []
    out, unparsed = {}, []

    def put(zone, label, cell, note=''):
        key = provision_key(label)
        label = f'{label} {note}'
        value = parse_value(cell)
        if key and value:
            out.setdefault(zone, {}).setdefault(key[0], {**value, 'bound': key[1],
                                                         'label': ' '.join(str(label).split()), **source})
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
        return out, unparsed
    first_col = _zone_cells([r[0] for r in rows[1:]])
    if sum(1 for z in first_col if z) >= 1 and any(provision_key(c or '') for c in rows[0][1:]):
        # Zones down the side, provisions across the top.
        for zone, row in zip(first_col, rows[1:]):
            if zone:
                for label, cell in zip(rows[0][1:], row[1:]):
                    put(zone.strip('()'), label, cell)
        return out, unparsed
    zones = _title_zones(page_text)
    if zones and sum(1 for c in rows[0][1:] if provision_key(c or '')) >= 2:
        # One zone's table by building type (the Seaton zones): provisions across the top, a row per
        # building type. The first building type listed is kept, and its name goes in the label.
        group = ''
        for row in rows[1:]:
            name = ' '.join(str(row[0] or '').split())
            if not any(parse_value(c) for c in row[1:]):
                group = name
                continue
            for label, cell in zip(rows[0][1:], row[1:]):
                for zone in zones:
                    put(zone, label, cell, f'– {group} {name}')
        return out, unparsed
    if zones and sum(1 for r in rows if provision_key(r[0] or '')) >= 2:
        # One zone's table: provision | value (| more columns for the same zone's variants).
        for row in rows:
            for zone in zones:
                put(zone, row[0], next((c for c in row[1:] if parse_value(c)), None))
    return out, unparsed


def rules_by_zone_row(table, source: dict) -> dict:
    """{zone: {provision: rule}} from a table with a row per zone and the zone's symbol in a column of
    its own, as the older exception zones set out their standards ("Figure 1").

    Such a table has a heading two rows deep ("Minimum Yards" over "Front", "Side and Flankage",
    "Rear"), and cells merged down a column read as blank below the first row, so a blank cell takes
    the value above it.
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
    out, above = {}, [''] * width
    for row in rows[first:]:
        above = [cell or kept for cell, kept in zip(row, above)]
        if not symbol(row[column]):
            continue
        rules = out.setdefault(row[column].strip('()'), {})
        for c, (label, cell) in enumerate(zip(labels, above)):
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
            if value:
                kind['provisions'].setdefault(key[0], {**value, 'bound': key[1], 'label': row[label], **source})
    return kinds, types


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
    lines, leads, previous = [], [], ''
    for row in text.split('\n'):
        # A row that carries on the sentence above it is judged with that row's words in front of it.
        carries_on = row.lstrip()[:1].islower() and previous.strip()[-1:] not in ('', '.', ':', ';')
        clauses = re.split(r';|(?<=\.)\s+(?=[A-Z(])', row)
        lines += clauses
        leads += [previous if carries_on else ''] + [''] * (len(clauses) - 1)
        previous = row
    for i, line in enumerate(lines):
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
        named = None
        if LABEL_ONLY.fullmatch(after) and i + 1 < len(lines):
            # The label ends its line and the value opens the next: "INTERIOR SIDE YARD WIDTH:" then
            # "minimum 1.2 metres each side", or 'on lands designated "S1" and "S2": 4.5 metres', in
            # which case the value is kept for the zones named and no others.
            after = lines[i + 1]
            named = re.match(r'\s*on lands designated\s+(.+?):', after, re.I)
            line, after = f'{line} {after}', after[named.end():] if named else after
        if not DIRECTLY_STATED.match(after):
            continue
        value = parse_value(after)
        if value and value['value'] > 60 and value['unit'] != 'm':
            continue  # a page or section number, not a yard: "FRONT YARD DEPTH (minimum): 164"
        if value and key[0] not in rules:
            rules[key[0]] = {**value, 'bound': key[1], 'label': ' '.join(line.split())[:200], **source}
            if named:
                rules[key[0]]['applies_to'] = re.findall(ZONE_TOKEN, named.group(1).upper())
    return rules


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
        begin, end = head.end(), head.end() + len(body)
        for (start, number), (stop, _) in zip(offsets, offsets[1:] + [(len(text), None)]):
            if max(start, begin) < min(stop, end):
                part = text[max(start, begin):min(stop, end)]
                for key, rule in rules_from_text(part, {**source, 'page': number}).items():
                    entry['provisions'].setdefault(key, rule)
    return found


def extract(documents: list[dict], store: Path) -> dict:
    """zone_rules.json content from the stored zoning by-law documents."""
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None
    zones, exceptions, unparsed, read = {}, {}, [], []
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
        if pdfplumber and path.exists():
            try:
                with pdfplumber.open(path) as pdf:
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
                            cells, where = table.extract(), {**source, 'page': number}
                            found, missed = rules_from_table(cells, page_text, where)
                            unparsed += missed
                            for zone, rules in found.items():
                                for key, rule in rules.items():
                                    zones.setdefault(zone, {}).setdefault(key, rule)
                            # A table of zones by row belongs to the exception it sits in: the last
                            # heading above it on the page, or the section open at the top of the page.
                            code, named = opened[number - 1] if number <= len(opened) else (None, None)
                            marks = [(h['top'], 'X', h) for h in heads] + [(h['top'], 'Z', h) for h in zoned]
                            for top, kind, mark in sorted(marks, key=lambda m: m[0]):
                                if top < table.bbox[1]:
                                    code, named = ((f"X{int(mark['groups'][0])}", None) if kind == 'X'
                                                   else (code, mark['groups'][0]))
                            for zone, rules in (rules_by_zone_row(cells, where) if code else {}).items():
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
                kept = exceptions[code].setdefault('by_zone', {}).setdefault(zone, {})
                for key, rule in rules.items():
                    kept.setdefault(key, rule)
        for code, by_type in typed.items():
            if code in exceptions:
                exceptions[code].setdefault('by_lot_type', {}).update(by_type)
    return {'zones': zones, 'exceptions': exceptions, 'unparsed': unparsed[:500], 'documents_read': read,
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
