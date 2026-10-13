"""Scrape Pickering zoning, parcel and overlay data, and the by-laws, to local disk.

Run this on the home server (it needs internet access); the API reads what it
writes. Nothing here is a zoning opinion: it keeps the city's own data, with
where and when each file came from, so a lookup can cite it.

    python scripts/scrape_pickering_zoning.py                # default store
    python scripts/scrape_pickering_zoning.py --out /srv/pickering --all-layers

What it pulls, mapped to the zoning-review steps the lookup answers:

1. Property identification: parcel fabric, address points, roll/PIN tables.
2. Existing zoning and Official Plan context, and overlays: floodplain and
   conservation-authority regulation, natural heritage, cultural heritage,
   easements and utility corridors, rail, Greenbelt / Oak Ridges Moraine /
   Seaton / federal lands.
4. Site characteristics: servicing (water, sanitary, storm) and topography.
6. Frameworks: the zoning by-law and Official Plan documents (PDF and text),
   the Provincial Planning Statement and O. Reg. 545/06.

Layers are found by walking the ArcGIS REST directory and matching layer
names, so a renamed or added city layer is still picked up. Every layer the
server publishes is listed in catalog.json, matched or not.
"""
import argparse
import hashlib
import html.parser
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / 'data' / 'municipal' / 'pickering'

ARCGIS_ROOTS = ['https://maps.pickering.ca/arcgisinter/rest/services']
# West, south, east, north in WGS84: the City with a margin. Sources beyond the
# City's own server are clipped to it, so a provincial layer brings only Pickering.
PICKERING_BBOX = (-79.23, 43.79, -78.95, 44.04)
# Regional, conservation-authority and provincial layers the City server may not carry.
EXTERNAL_SOURCES = [
    {'label': 'Durham Region Official Plan and open data',  # incl. Oak Ridges Moraine, railways, MTSAs
     'url': 'https://maps.durham.ca/arcgis/rest/services/Open_Data'},
    {'label': 'TRCA regulation limit (O. Reg. 41/24)',
     'url': 'https://services1.arcgis.com/d0ZCwU7eGKVeNiEE/ArcGIS/rest/services/TRCA_Regulation_Limit2/FeatureServer'},
    {'label': 'Ontario Greenbelt (Land Information Ontario)',
     'url': 'https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open06/MapServer'},
]

# Pages crawled for by-law, Official Plan and provincial documents. Links on
# them are followed one level within the same site when they look relevant.
DOCUMENT_PAGES = [
    'https://www.pickering.ca/business-building-development/planning-and-development/zoning/',
    # Comprehensive Zoning By-law 8149/24 (in force 16 Dec 2024; replaced 2511, 2520, 3036, 3037,
    # 7364/14 Seaton and 7553/17 City Centre): the by-law, its schedules and the review record.
    'https://www.pickering.ca/en/city-hall/comprehensive-zoning-by-law-review.aspx',
    'https://letstalkpickering.ca/zonereview',
    'https://www.pickering.ca/business-building-development/planning-and-development/official-plan/',
    'https://www.pickering.ca/business-building-development/planning-and-development/sustainable-development/',
    'https://www.ontario.ca/page/provincial-planning-statement-2024',
    'https://www.ontario.ca/laws/regulation/060545',
]
# Council meetings, where every amendment to the zoning by-law is passed as a by-law.
ESCRIBE = 'https://pub-pickering.escribemeetings.com'
ESCRIBE_SINCE = '2024-12-01'
ZONING_BYLAW_TEXT = re.compile(r'8149/24|zoning by-?law|amend\w* (by-?law|schedule)|zone (category|symbol)', re.I)
DOCUMENT_LINK = re.compile(r'zoning|by-?law|official[-_ ]?plan|planning[-_ ]statement|greenbelt|moraine|seaton'
                           r'|heritage|secondary[-_ ]plan|site[-_ ]plan|complete[-_ ]application|060545', re.I)

# First match wins, so specific overlays come before the broad "zoning" and
# "official plan" words that their layer names may also contain.
CATEGORIES = [
    ('provincial_plans', r'greenbelt|oak ridges|moraine|seaton|airport|federal lands|source water|wellhead'),
    ('floodplain', r'flood|regulat\w* (area|limit)|hazard|erosion|\btrca\b|\bcloca\b|shoreline'),
    ('rail', r'\brail|railway|\bcn\b|\bcp\b|metrolinx|go transit'),
    ('natural_heritage', r'natural heritage|wetland|woodland|woodlot|watercourse|stream|valley|environmental'
                         r'|\besa\b|\bansi\b|significant|natural (area|feature|system)|\btrees?\b'),
    ('heritage', r'heritage|archaeolog'),
    ('easements', r'easement|right[- ]of[- ]way|hydro corridor|utility corridor|transmission'),
    ('servicing', r'water ?main|sanitary|storm|sewer|hydrant|servic'),
    ('topography', r'contour|elevation|topograph|\bdem\b|lidar|slope'),
    ('zoning', r'zon(e|ing)|by-?law|exception'),
    ('official_plan', r'official plan|land use|designation|secondary plan|urban (boundary|area)|settlement'),
    ('parcels', r'parcel|propert(y|ies)|\blots?\b|cadastr|assessment|\broll\b|\bpin\b|lot fabric|ownership'),
    ('addresses', r'address|civic'),
    ('neighbourhoods', r'neighbou?rhood|\bwards?\b|communit(y|ies)'),
]

USER_AGENT = 'Mozilla/5.0 EnerZen-municipal-data (zoning research)'
PAGE = 500  # objectIds per query; under every ArcGIS default maxRecordCount
PAGINATION = re.compile(r'\bnext\b|›|»|\bpage=\d+|^\d+$', re.I)
KEEP_SNAPSHOTS = 2


def classify(name: str) -> str | None:
    # Service names come as OfficialPlanConsolidation2024_Map1 or TRCA_Regulation_Limit2.
    name = re.sub(r'(?<=[a-z])(?=[A-Z])|_', ' ', name)
    for category, pattern in CATEGORIES:
        if re.search(pattern, name, re.I):
            return category
    return None


def slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:80] or 'item'


class Fetcher:
    def __init__(self, delay: float = 0.2, retries: int = 3, timeout: int = 60):
        self.delay, self.retries, self.timeout = delay, retries, timeout

    def get(self, url: str, data: dict | None = None) -> bytes:
        body = urlencode(data).encode() if data is not None else None
        for attempt in range(self.retries):
            try:
                time.sleep(self.delay)
                with urlopen(Request(url, data=body, headers={'User-Agent': USER_AGENT}), timeout=self.timeout) as r:
                    return r.read()
            except HTTPError as exc:
                if exc.code < 500 or attempt == self.retries - 1:
                    raise
            except (URLError, TimeoutError):
                if attempt == self.retries - 1:
                    raise
            time.sleep(2 ** attempt)
        raise RuntimeError('unreachable')

    def json(self, url: str, **params) -> dict:
        params.setdefault('f', 'json')
        # Long objectIds lists go in a POST body; ArcGIS accepts both.
        if sum(len(str(v)) for v in params.values()) > 1500:
            value = json.loads(self.get(url, data=params))
        else:
            value = json.loads(self.get(f'{url}?{urlencode(params)}'))
        if isinstance(value, dict) and 'error' in value:
            raise ValueError(f"{url}: {value['error']}")
        return value


# ── ArcGIS ──────────────────────────────────────────────────────────────────

def walk_services(fetch: Fetcher, root: str) -> list[str]:
    """Every MapServer/FeatureServer URL under an ArcGIS REST root, folder, or a service itself."""
    if re.search(r'/(MapServer|FeatureServer)/?$', root):
        return [root.rstrip('/')]
    marker = re.search(r'/rest/services', root, re.I)
    base = root[:marker.end()] if marker else root
    found, folders = [], [root[len(base):].strip('/')]
    while folders:
        folder = folders.pop()
        listing = fetch.json(f'{base}/{folder}'.rstrip('/'))
        # Folder names are listed in full from the root, and relative to the folder elsewhere.
        folders += [f if '/' in f or not folder else f'{folder}/{f}' for f in listing.get('folders', [])]
        for service in listing.get('services', []):
            if service.get('type') in ('MapServer', 'FeatureServer'):
                found.append(f"{base}/{service['name']}/{service['type']}")
    return sorted(set(found))


def _bbox_params(bbox) -> dict:
    if not bbox:
        return {}
    return {'geometry': ','.join(map(str, bbox)), 'geometryType': 'esriGeometryEnvelope', 'inSR': '4326',
            'spatialRel': 'esriSpatialRelIntersects'}


def list_layers(fetch: Fetcher, service_url: str, bbox=None, source: str = 'City of Pickering') -> list[dict]:
    info = fetch.json(service_url)
    layers = []
    for entry in info.get('layers', []) + info.get('tables', []):
        if entry.get('subLayerIds'):  # group layer: its children are listed separately
            continue
        url = f"{service_url}/{entry['id']}"
        try:
            detail = fetch.json(url)
        except Exception as exc:  # one broken layer must not stop the walk
            layers.append({'url': url, 'name': entry.get('name'), 'error': repr(exc)})
            continue
        if detail.get('type') not in ('Feature Layer', 'Table'):
            continue
        try:
            count = fetch.json(f'{url}/query', where='1=1', returnCountOnly='true', **_bbox_params(bbox))['count']
        except Exception:
            count = None
        layers.append({
            'url': url, 'service': service_url, 'id': entry['id'], 'name': detail.get('name', entry.get('name')),
            'type': detail.get('type'), 'geometry_type': detail.get('geometryType'),
            'description': (detail.get('description') or '')[:1000], 'copyright': detail.get('copyrightText'),
            'fields': [{'name': f['name'], 'alias': f.get('alias'), 'type': f.get('type')}
                       for f in detail.get('fields') or []],
            'feature_count': count, 'source': source, 'bbox': bbox,
            'category': classify(detail.get('name', entry.get('name', ''))) or classify(service_url.split('/rest/services/')[-1]),
        })
    return layers


def _ring_area(ring):
    return sum(x1 * y2 - x2 * y1 for (x1, y1, *_), (x2, y2, *_) in zip(ring, ring[1:])) / 2


def esri_to_geojson(geometry: dict | None) -> dict | None:
    """Esri JSON geometry (already in WGS84) to GeoJSON, for servers without f=geojson."""
    if not geometry:
        return None
    if 'x' in geometry:
        return {'type': 'Point', 'coordinates': [geometry['x'], geometry['y']]}
    if 'points' in geometry:
        return {'type': 'MultiPoint', 'coordinates': [p[:2] for p in geometry['points']]}
    if 'paths' in geometry:
        return {'type': 'MultiLineString', 'coordinates': [[p[:2] for p in path] for path in geometry['paths']]}
    if 'rings' in geometry:
        # Esri outer rings run clockwise (negative signed area), holes counter-clockwise.
        polygons = []
        for ring in geometry['rings']:
            ring = [p[:2] for p in ring]
            if _ring_area(ring) <= 0 or not polygons:
                polygons.append([ring])
            else:
                polygons[-1].append(ring)
        return {'type': 'MultiPolygon', 'coordinates': polygons}
    return None


def _features(page: dict, id_field: str) -> list[dict]:
    return [{'type': 'Feature', 'id': f.get('attributes', {}).get(id_field), 'properties': f.get('attributes', {}),
             'geometry': esri_to_geojson(f.get('geometry'))} for f in page.get('features', [])]


def download_layer(fetch: Fetcher, layer: dict, path: Path) -> dict:
    """All features of one layer, in WGS84, as GeoJSON; checks every object id arrived.

    Pages that come back short (a server-side record cap, a dropped response) are
    retried in smaller pieces down to one feature, so the count either matches the
    server's or the shortfall is reported, never silently lost.
    """
    url = f"{layer['url']}/query"
    ids = fetch.json(url, where='1=1', returnIdsOnly='true', **_bbox_params(layer.get('bbox')))
    id_field, object_ids = ids.get('objectIdFieldName', 'OBJECTID'), sorted(ids.get('objectIds') or [])
    features, got = [], set()

    def pull(chunk):
        try:
            page = fetch.json(url, objectIds=','.join(map(str, chunk)), outFields='*', outSR='4326',
                              returnGeometry='true')
        except Exception:
            page = {}
        for feature in _features(page, id_field):
            if feature['id'] not in got:
                got.add(feature['id'])
                features.append(feature)

    for start in range(0, len(object_ids), PAGE):
        pull(object_ids[start:start + PAGE])
    for size in (50, 1):
        missing = [i for i in object_ids if i not in got]
        for start in range(0, len(missing), size):
            pull(missing[start:start + size])
    missing = [i for i in object_ids if i not in got]
    path.write_text(json.dumps({'type': 'FeatureCollection', 'name': layer['name'], 'source_url': layer['url'],
                                'features': features}), encoding='utf-8')
    return {'features': len(features), 'expected': len(object_ids), 'server_count': layer.get('feature_count'),
            'missing_ids': missing[:100], 'complete': not missing and
            (layer.get('feature_count') is None or layer['feature_count'] == len(features))}


# ── Documents ───────────────────────────────────────────────────────────────

class _Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._href, self._text = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self._href, self._text = dict(attrs).get('href'), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self._href:
            self.links.append((self._href, ' '.join(''.join(self._text).split())))
            self._href = None


def page_links(base: str, html_text: str) -> list[tuple[str, str]]:
    parser = _Links()
    parser.feed(html_text)
    return [(urljoin(base, href).split('#')[0], text) for href, text in parser.links
            if not href.startswith(('mailto:', 'tel:', 'javascript:'))]


def pdf_pages(path: Path, ocr: bool = True) -> tuple[list[str] | None, list[int]]:
    """Text of each page, and which pages needed OCR (scanned by-laws have no text layer).

    OCR runs only where pytesseract, Tesseract and pypdfium2 are installed (the
    scraper image has them); otherwise scanned pages stay empty and are reported.
    """
    try:
        from pypdf import PdfReader
        pages = [page.extract_text() or '' for page in PdfReader(path).pages]
    except Exception:
        return None, []
    blank = [i for i, text in enumerate(pages) if len(text.strip()) < 20]
    if not (blank and ocr):
        return pages, []
    try:
        import pypdfium2
        import pytesseract
        document = pypdfium2.PdfDocument(str(path))
        for i in blank:
            pages[i] = pytesseract.image_to_string(document[i].render(scale=2.5).to_pil())
        return pages, blank
    except Exception:
        return pages, []


def collect_documents(fetch: Fetcher, out: Path, pages: list[str], errors: list, ocr: bool = True,
                      docs_dir: Path | None = None) -> list[dict]:
    """Save each listed page, the relevant pages it links to, and every PDF they link to."""
    docs_dir = docs_dir or out / 'documents'
    docs_dir.mkdir(parents=True, exist_ok=True)
    queue, seen, documents = [(url, 'seed page', 0) for url in pages], set(), []
    while queue:
        url, title, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            body = fetch.get(url)
        except Exception as exc:
            errors.append({'url': url, 'error': repr(exc)})
            continue
        is_pdf = body[:5] == b'%PDF-' or urlparse(url).path.lower().endswith('.pdf')
        name = slug(Path(urlparse(url).path).stem or urlparse(url).netloc)
        path = docs_dir / f"{name}-{hashlib.sha256(url.encode()).hexdigest()[:8]}{'.pdf' if is_pdf else '.html'}"
        path.write_bytes(body)
        entry = {'url': url, 'title': title, 'file': str(path.relative_to(out)), 'kind': 'pdf' if is_pdf else 'html',
                 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
        if is_pdf:
            text, ocr_pages = pdf_pages(path, ocr)
            if text is not None:
                text_path = path.with_suffix('.pages.json')
                text_path.write_text(json.dumps(text), encoding='utf-8')
                entry.update(pages=len(text), text_file=str(text_path.relative_to(out)), ocr_pages=len(ocr_pages),
                             blank_pages=sum(1 for t in text if len(t.strip()) < 20))
        else:
            html_text = body.decode('utf-8', 'replace')
            match = re.search(r'<title>(.*?)</title>', html_text, re.I | re.S)
            entry['title'] = ' '.join(match.group(1).split()) if match else title
            # On a zoning / by-law / plan page every PDF is relevant; elsewhere only the ones that say so.
            planning_page = bool(DOCUMENT_LINK.search(f"{urlparse(url).path} {entry['title']}"))
            for link, text in page_links(url, html_text):
                same_site = urlparse(link).netloc == urlparse(url).netloc
                described = DOCUMENT_LINK.search(f'{link} {text}')
                if link.lower().split('?')[0].endswith('.pdf') and (planning_page or described):
                    queue.append((link, text or Path(urlparse(link).path).name, depth + 1))
                elif same_site and planning_page and PAGINATION.search(f'{text} {urlparse(link).query}') \
                        and link.split('?')[0] == url.split('?')[0]:
                    queue.append((link, entry['title'], depth))  # next page of the same listing
                elif depth == 0 and same_site and described:
                    queue.append((link, text, depth + 1))
        documents.append(entry)
    return documents


def council_meetings(fetch: Fetcher, base: str, since: str) -> list[str]:
    """Meeting page URLs on an eScribe site since a date, from its calendar service or its year pages."""
    until = f'{datetime.now(timezone.utc).year + 1}-12-31'
    urls = []
    try:
        body = json.dumps({'calendarStartDate': since, 'calendarEndDate': until}).encode()
        request = Request(f'{base}/MeetingsCalendarView.aspx/GetCalendarMeetings', data=body,
                          headers={'User-Agent': USER_AGENT, 'Content-Type': 'application/json; charset=utf-8'})
        with urlopen(request, timeout=fetch.timeout) as response:
            meetings = json.load(response).get('d') or []
        for meeting in meetings:
            url = meeting.get('Url') or meeting.get('url') or ''
            if not url and meeting.get('ID'):
                url = f"Meeting.aspx?Id={meeting['ID']}&Agenda=Agenda&lang=English"
            if url:
                urls.append(urljoin(base + '/', url))
    except Exception:
        pass
    if not urls:  # older eScribe sites list meetings in plain HTML by year
        for year in range(int(since[:4]), int(until[:4]) + 1):
            try:
                html_text = fetch.get(f'{base}/?Year={year}').decode('utf-8', 'replace')
            except Exception:
                continue
            urls += [link for link, _ in page_links(f'{base}/', html_text) if 'Meeting.aspx' in link]
    seen, unique = set(), []
    for url in urls:
        key = re.sub(r'&(Agenda|lang)=[^&]*', '', url)
        if key not in seen:
            seen.add(key)
            unique.append(url)
    return unique


def collect_council_bylaws(fetch: Fetcher, out: Path, base: str, errors: list, since: str = ESCRIBE_SINCE,
                           ocr: bool = True, docs_dir: Path | None = None) -> list[dict]:
    """Every by-law attached to a council agenda since the zoning by-law came into force that amends zoning.

    An attachment is downloaded when its link names a by-law, and kept only when its
    own text speaks of the zoning by-law; everything else is deleted again.
    """
    docs_dir = docs_dir or out / 'documents' / 'council'
    docs_dir.mkdir(parents=True, exist_ok=True)
    kept, seen = [], set()
    for meeting in council_meetings(fetch, base, since):
        try:
            html_text = fetch.get(meeting).decode('utf-8', 'replace')
        except Exception as exc:
            errors.append({'url': meeting, 'error': repr(exc)})
            continue
        for link, text in page_links(meeting, html_text):
            if 'FileStream.ashx' not in link or not re.search(r'by-?law', text, re.I) or link in seen:
                continue
            seen.add(link)
            try:
                body = fetch.get(link)
            except Exception as exc:
                errors.append({'url': link, 'error': repr(exc)})
                continue
            if body[:5] != b'%PDF-':
                continue
            document_id = re.search(r'DocumentId=(\d+)', link)
            path = docs_dir / f"{slug(text)[:60]}-{document_id.group(1) if document_id else hashlib.sha256(link.encode()).hexdigest()[:8]}.pdf"
            path.write_bytes(body)
            pages, ocr_pages = pdf_pages(path, ocr)
            if not pages or not ZONING_BYLAW_TEXT.search(' '.join(pages)):
                path.unlink()
                continue
            number = re.search(r'By-?law (?:No\.? ?)?(\d{3,4}/\d{2})', ' '.join(pages[:2]), re.I)
            text_path = path.with_suffix('.pages.json')
            text_path.write_text(json.dumps(pages), encoding='utf-8')
            kept.append({'url': link, 'title': f"Zoning amendment By-law {number.group(1)}" if number else text,
                         'link_text': text, 'meeting': meeting, 'file': str(path.relative_to(out)), 'kind': 'pdf',
                         'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body), 'pages': len(pages),
                         'text_file': str(text_path.relative_to(out)), 'ocr_pages': len(ocr_pages),
                         'blank_pages': sum(1 for t in pages if len(t.strip()) < 20), 'source': 'council'})
    return kept


# ── Run ─────────────────────────────────────────────────────────────────────

def bylaw_numbers_in(layer_path: Path) -> set[str]:
    """By-law numbers the City's zoning features cite (e.g. 3036, 7364/14)."""
    numbers = set()
    for feature in json.loads(layer_path.read_text(encoding='utf-8'))['features']:
        for key, value in (feature.get('properties') or {}).items():
            if re.search(r'law|amend|^bl|_bl', key, re.I):
                numbers.update(re.findall(r'\b\d{3,4}/\d{2,4}\b|\b\d{4}\b', str(value)))
    return numbers


def completeness(out: Path, catalog: list, layers: list, documents: list, errors: list) -> dict:
    """Everything that would make this copy less than all of the City's published data."""
    downloaded = {l['url'] for l in layers}
    cited = set()
    for layer in layers:
        if layer['category'] == 'zoning':
            cited |= bylaw_numbers_in(out / layer['file'])
    labels = ' '.join(f"{d['title']} {d['url']}" for d in documents)
    texts = ' '.join(Path(d['file']).name for d in documents)
    missing_bylaws = sorted(n for n in cited if not re.search(rf'(?<!\d){re.escape(n)}(?!\d)', f'{labels} {texts}'))
    report = {
        'catalog_layers': len(catalog),
        'not_downloaded': [{'name': l.get('name'), 'url': l['url'], 'reason': l.get('error', 'skipped')}
                           for l in catalog if l['url'] not in downloaded and l.get('feature_count') != 0],
        'incomplete_layers': [{'name': l['name'], 'url': l['url'], 'features': l['features'],
                               'expected': l['expected'], 'server_count': l['server_count']}
                              for l in layers if not l['complete']],
        'cited_bylaws': sorted(cited), 'missing_bylaws': missing_bylaws,
        'pdfs_without_text': [d['url'] for d in documents if d['kind'] == 'pdf' and 'text_file' not in d],
        'pdfs_with_blank_pages': [{'url': d['url'], 'blank_pages': d['blank_pages']}
                                  for d in documents if d.get('blank_pages')],
        'errors': len(errors),
    }
    report['complete'] = not (report['not_downloaded'] or report['incomplete_layers'] or missing_bylaws
                              or report['pdfs_without_text'] or report['pdfs_with_blank_pages'] or errors)
    return report


def _write_json(path: Path, value):
    """Write then rename, so a reader never sees half a file."""
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=1), encoding='utf-8')
    tmp.replace(path)


def scrape(out: Path, arcgis_roots=ARCGIS_ROOTS, document_pages=DOCUMENT_PAGES, all_layers=True,
           fetch: Fetcher | None = None, log=print, ocr: bool = True, escribe: str | None = ESCRIBE) -> dict:
    """Download into a new snapshot folder, then point manifest.json at it.

    The API keeps serving the previous snapshot until the new manifest lands, and
    the last KEEP_SNAPSHOTS runs are kept for comparison.
    """
    fetch = fetch or Fetcher()
    started = datetime.now(timezone.utc)
    snapshot = Path('snapshots') / started.strftime('%Y%m%dT%H%M%SZ')
    (out / snapshot / 'layers').mkdir(parents=True, exist_ok=True)
    errors, catalog = [], []
    sources = [{'url': r, 'label': 'City of Pickering', 'bbox': None} if isinstance(r, str) else
               {'bbox': PICKERING_BBOX, **r} for r in arcgis_roots]
    for source in sources:
        try:
            services = walk_services(fetch, source['url'])
        except Exception as exc:
            errors.append({'url': source['url'], 'error': repr(exc)})
            continue
        for service in services:
            log(f'service {service}')
            try:
                catalog += list_layers(fetch, service, bbox=source['bbox'], source=source['label'])
            except Exception as exc:
                errors.append({'url': service, 'error': repr(exc)})
    _write_json(out / snapshot / 'catalog.json', catalog)

    downloaded = []
    for layer in catalog:
        if 'error' in layer or not (all_layers or layer['category']) or layer['feature_count'] == 0:
            continue
        name = f"{layer['category'] or 'other'}--{slug(layer['name'])}-{slug(urlparse(layer['url']).path)[-24:]}"
        file = str(snapshot / 'layers' / f'{name}.geojson')
        log(f"layer {layer['name']} ({layer['category'] or 'other'}, {layer['feature_count']} features)")
        try:
            result = download_layer(fetch, layer, out / file)
        except Exception as exc:
            errors.append({'url': layer['url'], 'error': repr(exc)})
            continue
        if not result['complete']:
            log(f"  incomplete: {result['features']} of {result['expected']}")
        downloaded.append({**{k: layer[k] for k in ('url', 'name', 'category', 'geometry_type', 'type', 'source')},
                           'file': file, **result,
                           'sha256': hashlib.sha256((out / file).read_bytes()).hexdigest()})

    log('documents')
    documents = collect_documents(fetch, out, document_pages, errors, ocr=ocr, docs_dir=out / snapshot / 'documents')
    if escribe:
        log('council by-laws')
        documents += collect_council_bylaws(fetch, out, escribe, errors, ocr=ocr,
                                            docs_dir=out / snapshot / 'documents' / 'council')
    report = completeness(out, catalog, downloaded, documents, errors)
    manifest = {
        'municipality': 'Pickering',
        'retrieved_at': started.isoformat(timespec='seconds'),
        'finished_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'snapshot': str(snapshot), 'catalog_file': str(snapshot / 'catalog.json'),
        'arcgis_roots': sources, 'document_pages': document_pages,
        'layers': downloaded, 'documents': documents, 'errors': errors,
        'catalog_layers': len(catalog), 'completeness': report,
        'licence': 'City of Pickering Open Data Licence; provincial documents under their own terms.',
        'note': 'Raw municipal data for preliminary review only; not a zoning determination.',
    }
    _write_json(out / snapshot / 'manifest.json', manifest)
    if downloaded:  # never replace a working copy with an empty run (e.g. the city server was down)
        _write_json(out / 'manifest.json', manifest)
        _write_json(out / 'catalog.json', catalog)
        runs = sorted((out / 'snapshots').iterdir())
        for old in runs[:-KEEP_SNAPSHOTS]:
            shutil.rmtree(old, ignore_errors=True)
    return manifest


def verify(out: Path) -> dict:
    """Re-check the stored copy: every file present with its recorded checksum, and the completeness report."""
    manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    damaged = []
    for entry in manifest['layers'] + manifest['documents']:
        path = out / entry['file']
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            damaged.append(entry['file'])
    report = dict(manifest.get('completeness') or {})
    report.update(retrieved_at=manifest['retrieved_at'], damaged_files=damaged,
                  layers=len(manifest['layers']), documents=len(manifest['documents']))
    report['complete'] = bool(report.get('complete')) and not damaged
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--matched-only', action='store_true',
                        help='download only layers matched to a review category (default: every layer)')
    parser.add_argument('--arcgis-root', action='append', default=[],
                        help='another ArcGIS REST root, folder or service, clipped to Pickering (repeatable)')
    parser.add_argument('--page', action='append', default=[], help='another document page to crawl (repeatable)')
    parser.add_argument('--city-only', action='store_true',
                        help='skip the Durham Region, TRCA and provincial layers clipped to Pickering')
    parser.add_argument('--skip-documents', action='store_true')
    parser.add_argument('--no-ocr', action='store_true')
    parser.add_argument('--skip-council', action='store_true', help='skip zoning amendments from council agendas')
    parser.add_argument('--verify', action='store_true', help='check the stored copy instead of downloading')
    args = parser.parse_args(argv)
    if args.verify:
        report = verify(args.out)
        print(json.dumps(report, indent=1))
        return 0 if report['complete'] else 2
    roots = ARCGIS_ROOTS + ([] if args.city_only else EXTERNAL_SOURCES) + \
        [{'url': url, 'label': url.split('/rest/')[0]} for url in args.arcgis_root]
    manifest = scrape(args.out, arcgis_roots=roots, all_layers=not args.matched_only,
                      document_pages=[] if args.skip_documents else DOCUMENT_PAGES + args.page, ocr=not args.no_ocr,
                      escribe=None if args.skip_documents or args.skip_council else ESCRIBE)
    by_category = {}
    for layer in manifest['layers']:
        key = layer['category'] or 'other'
        by_category[key] = by_category.get(key, 0) + 1
    report = manifest['completeness']
    print(json.dumps({'out': str(args.out), 'snapshot': manifest['snapshot'],
                      'catalog_layers': manifest['catalog_layers'], 'downloaded_layers': by_category,
                      'documents': len(manifest['documents']), 'errors': manifest['errors'][:20],
                      'complete': report['complete'],
                      'incomplete_layers': report['incomplete_layers'],
                      'missing_bylaws': report['missing_bylaws'],
                      'pdfs_with_blank_pages': len(report['pdfs_with_blank_pages'])}, indent=1))
    if not manifest['layers']:
        return 1
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    sys.exit(main())
