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

# Pages crawled for by-law, Official Plan and provincial documents. Links on
# them are followed one level within the same site when they look relevant.
DOCUMENT_PAGES = [
    'https://www.pickering.ca/business-building-development/planning-and-development/zoning/',
    'https://www.pickering.ca/business-building-development/planning-and-development/official-plan/',
    'https://www.pickering.ca/business-building-development/planning-and-development/sustainable-development/',
    'https://www.ontario.ca/page/provincial-planning-statement-2024',
    'https://www.ontario.ca/laws/regulation/060545',
]
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


def classify(name: str) -> str | None:
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
    """Every MapServer/FeatureServer URL under an ArcGIS REST root."""
    found, folders = [], ['']
    while folders:
        folder = folders.pop()
        listing = fetch.json(f'{root}/{folder}'.rstrip('/'))
        folders += [f'{folder}/{f}'.strip('/') if folder else f for f in listing.get('folders', [])]
        for service in listing.get('services', []):
            if service.get('type') in ('MapServer', 'FeatureServer'):
                found.append(f"{root}/{service['name']}/{service['type']}")
    return sorted(set(found))


def list_layers(fetch: Fetcher, service_url: str) -> list[dict]:
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
            count = fetch.json(f'{url}/query', where='1=1', returnCountOnly='true')['count']
        except Exception:
            count = None
        layers.append({
            'url': url, 'service': service_url, 'id': entry['id'], 'name': detail.get('name', entry.get('name')),
            'type': detail.get('type'), 'geometry_type': detail.get('geometryType'),
            'description': (detail.get('description') or '')[:1000], 'copyright': detail.get('copyrightText'),
            'fields': [{'name': f['name'], 'alias': f.get('alias'), 'type': f.get('type')}
                       for f in detail.get('fields') or []],
            'feature_count': count, 'category': classify(detail.get('name', entry.get('name', ''))),
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


def download_layer(fetch: Fetcher, layer: dict, path: Path) -> int:
    """All features of one layer, in WGS84, as a GeoJSON FeatureCollection."""
    url = f"{layer['url']}/query"
    ids = fetch.json(url, where='1=1', returnIdsOnly='true')
    id_field, object_ids = ids.get('objectIdFieldName', 'OBJECTID'), sorted(ids.get('objectIds') or [])
    features = []
    for start in range(0, len(object_ids), PAGE):
        chunk = ','.join(map(str, object_ids[start:start + PAGE]))
        page = fetch.json(url, objectIds=chunk, outFields='*', outSR='4326', returnGeometry='true')
        for feature in page.get('features', []):
            features.append({'type': 'Feature', 'id': feature.get('attributes', {}).get(id_field),
                             'properties': feature.get('attributes', {}),
                             'geometry': esri_to_geojson(feature.get('geometry'))})
    path.write_text(json.dumps({'type': 'FeatureCollection', 'name': layer['name'], 'source_url': layer['url'],
                                'features': features}), encoding='utf-8')
    return len(features)


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


def pdf_pages(path: Path) -> list[str] | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        return [page.extract_text() or '' for page in PdfReader(path).pages]
    except Exception:
        return None


def collect_documents(fetch: Fetcher, out: Path, pages: list[str], errors: list) -> list[dict]:
    """Save each listed page, the relevant pages it links to, and every PDF they link to."""
    docs_dir = out / 'documents'
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
            text = pdf_pages(path)
            if text is not None:
                text_path = path.with_suffix('.pages.json')
                text_path.write_text(json.dumps(text), encoding='utf-8')
                entry.update(pages=len(text), text_file=str(text_path.relative_to(out)))
        else:
            html_text = body.decode('utf-8', 'replace')
            match = re.search(r'<title>(.*?)</title>', html_text, re.I | re.S)
            entry['title'] = ' '.join(match.group(1).split()) if match else title
            for link, text in page_links(url, html_text):
                same_site = urlparse(link).netloc == urlparse(url).netloc
                if link.lower().split('?')[0].endswith('.pdf') and DOCUMENT_LINK.search(f'{link} {text}'):
                    queue.append((link, text or Path(urlparse(link).path).name, depth + 1))
                elif depth == 0 and same_site and DOCUMENT_LINK.search(f'{urlparse(link).path} {text}'):
                    queue.append((link, text, depth + 1))
        documents.append(entry)
    return documents


# ── Run ─────────────────────────────────────────────────────────────────────

def scrape(out: Path, arcgis_roots=ARCGIS_ROOTS, document_pages=DOCUMENT_PAGES, all_layers=False,
           fetch: Fetcher | None = None, log=print) -> dict:
    fetch = fetch or Fetcher()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'layers').mkdir(exist_ok=True)
    errors, catalog = [], []
    for root in arcgis_roots:
        try:
            services = walk_services(fetch, root)
        except Exception as exc:
            errors.append({'url': root, 'error': repr(exc)})
            continue
        for service in services:
            log(f'service {service}')
            try:
                catalog += list_layers(fetch, service)
            except Exception as exc:
                errors.append({'url': service, 'error': repr(exc)})
    (out / 'catalog.json').write_text(json.dumps(catalog, indent=1), encoding='utf-8')

    downloaded = []
    for layer in catalog:
        if 'error' in layer or not (all_layers or layer['category']):
            continue
        file = f"layers/{layer['category'] or 'other'}--{slug(layer['name'])}-{slug(urlparse(layer['url']).path)[-24:]}.geojson"
        log(f"layer {layer['name']} ({layer['category']}, {layer['feature_count']} features)")
        try:
            count = download_layer(fetch, layer, out / file)
        except Exception as exc:
            errors.append({'url': layer['url'], 'error': repr(exc)})
            continue
        downloaded.append({**{k: layer[k] for k in ('url', 'name', 'category', 'geometry_type', 'type')},
                           'file': file, 'features': count,
                           'sha256': hashlib.sha256((out / file).read_bytes()).hexdigest()})

    log('documents')
    documents = collect_documents(fetch, out, document_pages, errors)
    manifest = {
        'municipality': 'Pickering',
        'retrieved_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'arcgis_roots': arcgis_roots, 'document_pages': document_pages,
        'layers': downloaded, 'documents': documents, 'errors': errors,
        'catalog_layers': len(catalog),
        'licence': 'City of Pickering Open Data Licence; provincial documents under their own terms.',
        'note': 'Raw municipal data for preliminary review only; not a zoning determination.',
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--all-layers', action='store_true', help='also download layers no category matches')
    parser.add_argument('--skip-documents', action='store_true')
    args = parser.parse_args(argv)
    manifest = scrape(args.out, all_layers=args.all_layers,
                      document_pages=[] if args.skip_documents else DOCUMENT_PAGES)
    by_category = {}
    for layer in manifest['layers']:
        by_category[layer['category']] = by_category.get(layer['category'], 0) + 1
    print(json.dumps({'out': str(args.out), 'catalog_layers': manifest['catalog_layers'],
                      'downloaded_layers': by_category, 'documents': len(manifest['documents']),
                      'errors': len(manifest['errors'])}, indent=1))
    return 1 if not manifest['layers'] else 0


if __name__ == '__main__':
    sys.exit(main())
