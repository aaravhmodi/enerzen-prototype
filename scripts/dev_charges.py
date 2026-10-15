"""Scrape the development charges a new home in Pickering pays: City, Region of Durham and school boards.

Each authority posts its current rates as a pamphlet linked from its development charges
page; the pamphlet's file name changes every year, so the page is read for it on each run.
The rates are read from the pamphlet's own table, row by row, and written with the
pamphlet's address and effective date to dev_charges.json in the store.

    python scripts/dev_charges.py --store data/municipal/pickering
"""
import argparse
import datetime as dt
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

PAGES = [
    ('City of Pickering', 'https://www.pickering.ca/business-building-development/planning-and-development/development-charges/',
     r'developmentcharges?_?(citywide|city-wide|seaton\w*)[^"]*\.pdf'),
    ('Region of Durham', 'https://www.durham.ca/doing-business/planning-and-development/development-charges/',
     r'(region-wide|seaton)-development-charge-information[^"]*\.pdf'),
]
USER_AGENT = 'Mozilla/5.0 EnerZen-municipal-data (development charges research)'
# Each table's residential columns, keyed by the words its header puts first.
KINDS = ('single_semi', 'multiples', 'apartment_2_bed_plus', 'apartment_1_bed_or_less')
TABLE_END = re.compile(r'Applicable to Building Permit Applications Received Prior|COMMERCIAL USE|Non-Residential Development', re.I)
TABLE_START = re.compile(r'^(?:Per Residential Dwelling Unit|RESIDENTIAL DEVELOPMENT CHARGES|SEATON RESIDENTIAL)')


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def visible_lines(page) -> list[str]:
    """A pdfplumber page's text as it is seen. Pickering's pamphlet prints each year's new rates
    over last year's in another font, so a word covered by a word drawn later is dropped."""
    order = {(c['x0'], c['top'], c['text']): i for i, c in enumerate(page.chars)}
    words = page.extract_words(extra_attrs=['fontname'])
    for w in words:
        w['drawn'] = order.get((w['x0'], w['top'], w['text'][0]), 0)

    def covered(a, b):
        ix = min(a['x1'], b['x1']) - max(a['x0'], b['x0'])
        iy = min(a['bottom'], b['bottom']) - max(a['top'], b['top'])
        small = min((a['x1'] - a['x0']) * (a['bottom'] - a['top']), (b['x1'] - b['x0']) * (b['bottom'] - b['top']))
        return ix > 0 and iy > 0 and ix * iy > 0.4 * small

    kept = [w for w in words if not any(o['fontname'] != w['fontname'] and o['drawn'] > w['drawn'] and covered(w, o)
                                        for o in words)]
    lines = []
    for w in sorted(kept, key=lambda w: (w['top'], w['x0'])):
        if lines and abs(lines[-1][0] - w['top']) < 4:
            lines[-1][1].append(w)
        else:
            lines.append([w['top'], [w]])
    return [' '.join(w['text'] for w in sorted(ws, key=lambda w: w['x0'])) for _, ws in lines]


AMOUNT = re.compile(r'^\$?(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$')


def _row(line: str) -> tuple[str, list[float]] | None:
    """("Regional Roads", [27609, 21989, 16074, 9873]): a label, then its amounts at the end of the line."""
    tokens = line.replace('$ ', '$').split()
    while tokens and tokens[-1].lower() == 'n/a':
        tokens.pop()
    amounts = []
    while tokens and AMOUNT.match(tokens[-1]):
        amounts.insert(0, float(tokens.pop().lstrip('$').replace(',', '')))
    label = re.sub(r'(\s*\(\d\))+$|(?<=[a-z])\d$|\*$', '', ' '.join(tokens)).strip(' :*')
    return (label, amounts) if len(amounts) >= 3 and re.search('[A-Za-z]{3}', label) else None


def read_tables(lines: list[str]) -> dict | None:
    """{services: {service: {kind: $}}, total} from a pamphlet's first residential table, or None
    unless its rows add up to the table's own total.

    A row named "Total..." that equals the rows since the last subtotal is a subtotal, one that
    equals every row is the table's total, and any other (Seaton's "Total Soft Services") is a row.
    """
    start = next((i for i, l in enumerate(lines) if TABLE_START.search(l)), None)
    if start is None:
        return None
    header = ' '.join(lines[start:start + 8])
    # Durham lists medium density multiples second; Pickering puts "other multiples" last.
    # Durham lists medium density multiples second, and Seaton's water and sewer has one apartment
    # column; Pickering puts "other multiples" last.
    if 'Medium' in header:
        order = KINDS if header.count('Apartment') >= 2 else (KINDS[0], KINDS[1], 'apartment')
    else:
        order = (KINDS[0], KINDS[2], KINDS[3], KINDS[1])
    n = len(order)
    services, since, total, section = {}, [], None, ''
    near = lambda a, b: all(abs(x - y) <= 5 for x, y in zip(a, b))
    add = lambda rows: [sum(r[i] for r in rows) for i in range(n)]
    for line in lines[start + 1:]:
        if TABLE_END.search(line) or TABLE_START.search(line) or re.search(r'PER (SQUARE FOOT|NET HECTARE)', line):
            break
        row = _row(line)
        if not row or len(row[1]) < n:
            if re.fullmatch(r'[A-Za-z][A-Za-z -]{3,40}', line.strip()):
                section = line.strip()  # "Water Supply": a heading over rows that repeat their names
            continue
        label, amounts = row[0], row[1][:n]
        is_total = re.match(r'(sub)?total', label, re.I)
        # Read to the table's end: a first subtotal also equals every row read so far.
        if is_total and services and near(amounts, add(list(services.values()))):
            total, since = amounts, []
            continue
        if is_total and since and near(amounts, add(since)):
            since = []
            continue
        services[f'{section}: {label}' if label in services or section and 'DCs' in label else label] = amounts
        since.append(amounts)
    if total is None or not near(total, add(list(services.values()))):
        return None
    widen = lambda v: {**(lambda d: {k: d[k] for k in d if k != 'apartment'})(dict(zip(order, v))),
                       **({KINDS[2]: v[2], KINDS[3]: v[2]} if 'apartment' in order else {})}
    when = re.search(r'(?:Effective|Current as of)\s+(\w+ \d{1,2}, ?\d{4})', ' '.join(lines[start:start + 3]), re.I)
    return {'services': {k: widen(v) for k, v in services.items()}, 'total': widen(total),
            'effective': when.group(1) if when else None}


def read_pamphlet(pdf) -> dict | None:
    """The pamphlet's table read from its plain text, or from its visible words where a year's rates
    are printed over the last; the reading whose rows add up wins."""
    plain = [l for p in pdf.pages for l in (p.extract_text() or '').splitlines()]
    table = read_tables(plain) or read_tables([l for p in pdf.pages for l in visible_lines(p)])
    if table is None:
        return None
    text = ' '.join(plain)
    when = re.search(r'(?:Effective|Current as of)\s+(\w+ \d{1,2}, ?\d{4})', text, re.I)
    table['effective'] = table['effective'] or (when.group(1) if when else None)
    school = re.search(r'Education Development Charges.{0,900}?Residential.{0,200}?\$([\d,]+) \$([\d,]+) \$([\d,]+)', text, re.S)
    table['education'] = dict(zip(('public', 'catholic', 'total'), (float(g.replace(',', '')) for g in school.groups()))) if school else None
    return table


def scrape(store: Path) -> dict:
    import pdfplumber
    folder = store / 'dev_charges'
    folder.mkdir(parents=True, exist_ok=True)
    schedules, errors = [], []
    for authority, page_url, pattern in PAGES:
        try:
            html = fetch(page_url).decode('utf-8', 'replace')
        except Exception as exc:
            errors.append({'url': page_url, 'error': repr(exc)})
            continue
        links = {}
        for m in re.finditer(r'(https?://[^"\s]*?|/media/[^"\s]*?)' + pattern, html, re.I):
            url = m.group(0) if m.group(0).startswith('http') else 'https://' + page_url.split('/')[2] + m.group(0)
            links.setdefault(url.rsplit('/', 1)[1], url)  # the City's CDN and its own address serve the same file
        for name, url in sorted(links.items()):
            try:
                body = fetch(url)
                (folder / name).write_bytes(body)
                with pdfplumber.open(io.BytesIO(body)) as pdf:
                    table = read_pamphlet(pdf)
                if table is None:
                    errors.append({'url': url, 'error': 'no residential table that adds up to its total'})
                    continue
                schedules.append({'authority': authority, 'area': 'seaton' if 'seaton' in name.lower() else 'citywide',
                                  'url': url, 'file': f'dev_charges/{name}', 'source_page': page_url, **table})
            except Exception as exc:
                errors.append({'url': url, 'error': repr(exc)})
    result = {'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
              'schedules': schedules, 'errors': errors}
    if schedules:  # a failed run keeps the last good copy
        (store / 'dev_charges.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--store', type=Path, default=Path(__file__).resolve().parent.parent / 'data' / 'municipal' / 'pickering')
    result = scrape(parser.parse_args().store)
    print(json.dumps({'schedules': [(s['authority'], s['area'], s['effective'], len(s['services'])) for s in result['schedules']],
                      'errors': result['errors']}, indent=1))
    sys.exit(0 if len(result['schedules']) == 4 else 2)
