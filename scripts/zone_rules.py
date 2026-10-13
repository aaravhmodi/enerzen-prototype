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
    ('exterior_side_yard', r'exterior\s+side\s+yard|flankag\s?e', 'minimum'),
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


def rules_from_text(text: str, source: dict) -> dict:
    """Provisions stated in prose: "the minimum rear yard shall be 7.5 metres"."""
    rules = {}
    for line in re.split(r'\n|;|(?<=\.)\s+(?=[A-Z(])', text):
        key = provision_key(line)
        if not key:
            continue
        after = re.split(PROVISIONS[[p[0] for p in PROVISIONS].index(key[0])][1], line, maxsplit=1, flags=re.I)[-1]
        value = parse_value(after)
        if value and key[0] not in rules:
            rules[key[0]] = {**value, 'bound': key[1], 'label': ' '.join(line.split())[:200], **source}
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
        provisions = rules_from_text(body, {**source, 'page': page})
        entry = found.setdefault(code, {'heading': ' '.join(head.group(0).split())[:160], 'page': page,
                                        'provisions': {}, 'text': ' '.join(body.split())[:4000], **source})
        for key, rule in provisions.items():
            entry['provisions'].setdefault(key, rule)
    return found


def extract(documents: list[dict], store: Path) -> dict:
    """zone_rules.json content from the stored zoning by-law documents."""
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None
    zones, exceptions, unparsed, read = {}, {}, [], []
    for doc in documents:
        label = f"{doc.get('title', '')} {doc.get('url', '')}"
        if doc.get('kind') != 'pdf' or not re.search(r'zoning|by-?law|exception|8149', label, re.I):
            continue
        path = store / doc['file']
        pages = json.loads((store / doc['text_file']).read_text(encoding='utf-8')) if doc.get('text_file') else []
        source = {'document': doc.get('title'), 'file': doc['file'], 'url': doc.get('url')}
        read.append(doc['file'])
        if pdfplumber and path.exists():
            try:
                with pdfplumber.open(path) as pdf:
                    for number, page in enumerate(pdf.pages, 1):
                        page_text = page.extract_text() or (pages[number - 1] if number <= len(pages) else '')
                        for table in page.extract_tables():
                            found, missed = rules_from_table(table, page_text, {**source, 'page': number})
                            unparsed += missed
                            for zone, rules in found.items():
                                for key, rule in rules.items():
                                    zones.setdefault(zone, {}).setdefault(key, rule)
            except Exception as exc:
                unparsed.append({'file': doc['file'], 'error': repr(exc)})
        for code, entry in exceptions_from_pages(pages, source).items():
            current = exceptions.setdefault(code, entry)
            if current is not entry:  # an amendment restating an exception: later documents add provisions
                current.setdefault('also_in', []).append(entry['file'])
                for key, rule in entry['provisions'].items():
                    current['provisions'].setdefault(key, rule)
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
