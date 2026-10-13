"""Scrape a fake Pickering ArcGIS server and website, then look parcels up from the store."""
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from reportlab.pdfgen import canvas

from api.main import pickering_data_status, zoning_lookup
from engine import pickering_zoning
from scripts.scrape_pickering_zoning import Fetcher, classify, esri_to_geojson, scrape

LAT, LON = 43.84, -79.09
CITY = 'Pickering (Dunbarton)'


def square(lon, lat, half):
    # Clockwise, as Esri writes outer rings.
    return [[lon - half, lat - half], [lon - half, lat + half], [lon + half, lat + half],
            [lon + half, lat - half], [lon - half, lat - half]]


LAYERS = {
    0: ('Zoning', 'esriGeometryPolygon', [
        {'attributes': {'OBJECTID': 1, 'ZONE': 'R4', 'BYLAW': '3036', 'AREA_HA': 2018},
         'geometry': {'rings': [square(LON, LAT, 0.002)]}},
        {'attributes': {'OBJECTID': 2, 'ZONE': 'A', 'BYLAW': '2511'},
         'geometry': {'rings': [square(LON + 0.05, LAT, 0.002)]}},
        {'attributes': {'OBJECTID': 3, 'ZONE': 'C1', 'BYLAW': 'By-law 9999/21'},
         'geometry': {'rings': [square(LON - 0.05, LAT, 0.002)]}},
        {'attributes': {'OBJECTID': 4, 'ZONE': 'R3-7', 'BYLAW': '3036'},
         'geometry': {'rings': [square(LON + 0.0012, LAT, 0.0006)]}}]),
    1: ('Property Parcels', 'esriGeometryPolygon', [
        {'attributes': {'OBJECTID': 7, 'ADDRESS': '1 Test St', 'ROLL_NUM': '1801000000', 'LEGAL': 'LOT 5 PLAN 40M-1'},
         'geometry': {'rings': [square(LON, LAT, 0.0003)]}},
        {'attributes': {'OBJECTID': 8, 'ADDRESS': '3 Test St', 'ROLL_NUM': '1801000002'},
         'geometry': {'rings': [square(LON + 0.001, LAT, 0.0003)]}}]),
    2: ('CN Railway', 'esriGeometryPolyline', [
        {'attributes': {'OBJECTID': 1, 'OWNER': 'CN'},
         'geometry': {'paths': [[[LON - 0.01, LAT + 0.002], [LON + 0.01, LAT + 0.002]]]}}]),
    3: ('Building Footprints', 'esriGeometryPolygon', []),
}


REGION_FEATURES = [  # one centre in Pickering, one in Oshawa (outside the clip)
    {'attributes': {'OBJECTID': 1, 'Name': 'Pickering City Centre'}, 'geometry': {'rings': [square(LON, LAT, 0.004)]}},
    {'attributes': {'OBJECTID': 2, 'Name': 'Oshawa Centre'}, 'geometry': {'rings': [square(-78.86, 43.90, 0.004)]}},
]


def bylaw_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, 'Zoning By-law 3036 general provisions')
    pdf.showPage()
    pdf.drawString(72, 720, 'Section 5: R4 zone - minimum lot frontage 15 m')
    pdf.drawString(72, 700, 'Maximum building height 9.0 m')
    pdf.drawString(72, 680, 'Minimum rear yard depth 7.5 metres')
    pdf.drawString(72, 660, 'Permitted uses: detached dwelling, home occupation')
    pdf.drawString(72, 640, 'Parking is regulated elsewhere')
    pdf.save()
    return buffer.getvalue()


class FakeCity(BaseHTTPRequestHandler):
    pdf = bylaw_pdf()

    def log_message(self, *args):
        pass

    def send(self, body, kind='application/json'):
        body = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers['Content-Length'])
        self.route(parse_qs(self.rfile.read(length).decode()))

    def do_GET(self):
        self.route(parse_qs(urlparse(self.path).query))

    def route(self, q):
        path = urlparse(self.path).path
        q = {k: v[0] for k, v in q.items()}
        if path == '/region/rest/services/Open_Data':
            return self.send({'services': [{'name': 'Open_Data/OfficialPlan_Map1', 'type': 'MapServer'}]})
        region = '/region/rest/services/Open_Data/OfficialPlan_Map1/MapServer'
        if path == region:
            return self.send({'layers': [{'id': 0, 'name': 'Map 1 - Regional Centres'},
                                         {'id': 1, 'name': 'Oak Ridges Moraine'}]})
        if path.startswith(region + '/'):
            layer_id = int(path[len(region) + 1:].split('/')[0])
            features = [] if layer_id == 1 else REGION_FEATURES
            if 'geometry' in q:  # honour the envelope: first vertex inside it
                w, s_, e, n = map(float, q['geometry'].split(','))
                features = [f for f in features if w <= f['geometry']['rings'][0][0][0] <= e
                            and s_ <= f['geometry']['rings'][0][0][1] <= n]
            if path.endswith('/query'):
                if q.get('returnCountOnly'):
                    return self.send({'count': len(features)})
                if q.get('returnIdsOnly'):
                    return self.send({'objectIdFieldName': 'OBJECTID', 'objectIds': [f['attributes']['OBJECTID'] for f in features]})
                wanted = {int(i) for i in q['objectIds'].split(',')}
                return self.send({'features': [f for f in REGION_FEATURES if f['attributes']['OBJECTID'] in wanted]})
            return self.send({'name': ['Map 1 - Regional Centres', 'Oak Ridges Moraine'][layer_id], 'type': 'Feature Layer',
                              'geometryType': 'esriGeometryPolygon', 'fields': []})
        base = '/arcgis/rest/services'
        if path == base:
            return self.send({'folders': ['public'], 'services': []})
        if path == f'{base}/public':
            return self.send({'services': [{'name': 'public/OpenData', 'type': 'MapServer'},
                                           {'name': 'public/Imagery', 'type': 'ImageServer'}]})
        svc = f'{base}/public/OpenData/MapServer'
        if path == svc:
            return self.send({'layers': [{'id': i, 'name': n} for i, (n, _, _) in LAYERS.items()]
                              + [{'id': 9, 'name': 'Planning group', 'subLayerIds': [0, 1]}]})
        parts = path[len(svc) + 1:].split('/')
        if path.startswith(svc + '/') and int(parts[0]) in LAYERS:
            name, geometry_type, features = LAYERS[int(parts[0])]
            if len(parts) == 1:
                return self.send({'name': name, 'type': 'Feature Layer', 'geometryType': geometry_type,
                                  'fields': [{'name': k, 'type': 'esriFieldTypeString'}
                                             for k in (features[0]['attributes'] if features else {})]})
            if q.get('returnCountOnly'):
                return self.send({'count': len(features)})
            if q.get('returnIdsOnly'):
                return self.send({'objectIdFieldName': 'OBJECTID',
                                  'objectIds': [f['attributes']['OBJECTID'] for f in features]})
            wanted = sorted(int(i) for i in q['objectIds'].split(','))
            if parts[0] == '1' and len(wanted) > 1:
                wanted = wanted[:-1]  # a server that silently caps pages
            return self.send({'features': [f for f in features if f['attributes']['OBJECTID'] in wanted]})
        if path == '/site/zoning/' and q.get('page') == '2':
            return self.send(b'<html><title>Zoning | Pickering</title><a href="/files/2511.pdf">2511</a>', 'text/html')
        if path == '/site/zoning/':
            return self.send(b'<html><title>Zoning | Pickering</title><a href="/files/by-law-3036.pdf">Zoning '
                             b'By-law 3036</a><a href="/files/menu.pdf">Recreation guide</a>'
                             b'<a href="/site/official-plan/">Official Plan</a><a href="/site/parks/">Parks</a>'
                             b'<a href="/site/zoning/?page=2">Next</a>', 'text/html')

        if path == '/site/official-plan/':
            return self.send(b'<html><title>Official Plan</title></html>', 'text/html')
        if path in ('/files/by-law-3036.pdf', '/files/2511.pdf', '/files/menu.pdf'):
            return self.send(self.pdf, 'application/pdf')
        self.send_response(404)
        self.end_headers()


@pytest.fixture(scope='module')
def store(tmp_path_factory):
    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeCity)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = f'http://127.0.0.1:{server.server_port}'
    out = tmp_path_factory.mktemp('pickering')
    manifest = scrape(out, arcgis_roots=[f'{host}/arcgis/rest/services',
                                         {'url': f'{host}/region/rest/services/Open_Data', 'label': 'Region'}],
                      document_pages=[f'{host}/site/zoning/', f'{host}/site/missing/'],
                      fetch=Fetcher(delay=0, retries=1), log=lambda *_: None)
    server.shutdown()
    return out, manifest


@pytest.fixture
def use_store(store, monkeypatch):
    monkeypatch.setenv('PICKERING_DATA_DIR', str(store[0]))
    return store


def test_scrape_downloads_every_layer_and_proves_it(store):
    out, manifest = store
    assert {layer['category'] for layer in manifest['layers']} == {'zoning', 'parcels', 'rail', 'official_plan'}  # empty footprints skipped
    assert len(json.loads((out / 'catalog.json').read_text())) == 6
    parcels = next(l for l in manifest['layers'] if l['category'] == 'parcels')
    assert parcels['features'] == parcels['expected'] == 2 and parcels['complete']  # the capped page was retried
    report = manifest['completeness']
    assert report['cited_bylaws'] == ['2511', '3036', '9999/21'] and report['missing_bylaws'] == ['9999/21']
    assert not report['incomplete_layers'] and not report['not_downloaded']
    assert report['complete'] is False  # the missing by-law and the dead page keep it honest


def test_scrape_follows_listing_pages_and_takes_every_pdf_on_planning_pages(store):
    _, manifest = store
    docs = {d['url'].split('/', 3)[-1]: d for d in manifest['documents']}
    assert docs['files/by-law-3036.pdf']['pages'] == 2
    assert {'files/2511.pdf', 'files/menu.pdf', 'site/zoning/?page=2', 'site/official-plan/'} <= set(docs)
    assert not any('parks' in u for u in docs)
    assert [e['url'].endswith('/site/missing/') for e in manifest['errors']] == [True]


def test_verify_catches_damage_and_failed_runs_keep_the_good_copy(store, tmp_path):
    import shutil
    from scripts.scrape_pickering_zoning import verify
    out = tmp_path / 'copy'
    shutil.copytree(store[0], out)
    assert verify(out)['damaged_files'] == []
    layer = out / store[1]['layers'][0]['file']
    layer.write_text('{}')
    assert verify(out)['damaged_files'] == [store[1]['layers'][0]['file']]
    before = (out / 'manifest.json').read_text()
    scrape(out, arcgis_roots=['http://127.0.0.1:9/arcgis'], document_pages=[],
           fetch=Fetcher(delay=0, retries=1, timeout=2), log=lambda *_: None)
    assert (out / 'manifest.json').read_text() == before


def test_lookup_answers_the_review_steps(use_store):
    result = zoning_lookup('Pickering (Dunbarton)', LAT, LON)
    steps = result['steps']
    assert result['status'] == 'available'
    prop = steps['1_property_identification']['from_city_data']
    assert prop['address'] == '1 Test St' and prop['roll_number'] == '1801000000'
    assert 2500 < prop['area_m2'] < 3600  # ~0.0006 deg square at 43.84 N
    zoning = steps['2_existing_zoning_and_official_plan']
    assert zoning['zone_codes'] == ['R4'] and zoning['bylaw_numbers'] == ['3036']
    assert zoning['zoning'][0]['parcel_share_pct'] == 100.0
    rail = zoning['overlays']['rail']
    assert len(rail) == 1 and 150 < rail[0]['distance_m'] < 200
    assert 'rail' in steps['5_supporting_documents']['triggered_by_overlays']
    refs = steps['6_planning_frameworks']['zoning_bylaw_references']
    assert refs[0]['names_parcel_bylaw'] == ['3036'] and refs[0]['zone_pages'] == {'R4': [2]}
    json.dumps(result)  # the API can serialize it


def test_lookup_by_roll_number_or_address(use_store):
    by_roll = zoning_lookup(CITY, query='1801000002')
    assert by_roll['steps']['1_property_identification']['from_city_data']['address'] == '3 Test St'
    by_address = zoning_lookup(CITY, query='1 test st')
    assert by_address['matched_property']['value'] == '1 Test St'
    assert zoning_lookup(CITY, query='99 Nowhere Rd')['status'] == 'not_found'


def test_point_outside_city_data(use_store):
    assert zoning_lookup(CITY, 43.9, -79.0)['status'] == 'not_found'
    assert pickering_data_status()['layers']['rail'][0]['name'] == 'CN Railway'


def test_without_a_store_says_to_scrape(tmp_path, monkeypatch):
    monkeypatch.setenv('PICKERING_DATA_DIR', str(tmp_path))
    assert zoning_lookup(CITY, LAT, LON)['status'] == 'not_scraped'
    assert pickering_zoning.status()['status'] == 'not_scraped'


def test_layer_names_map_to_review_categories():
    assert classify('Zoning By-law 7364/14') == 'zoning'
    assert classify('TRCA Regulation Limit') == 'floodplain'
    assert classify('Greenbelt Plan Area') == 'provincial_plans'
    assert classify('Street Centreline') is None
    assert classify('Watercourses') == 'natural_heritage'


def test_esri_rings_become_polygons_with_holes():
    outer, hole = square(0, 0, 2), square(0, 0, 1)[::-1]
    geo = esri_to_geojson({'rings': [outer, hole, square(10, 0, 1)]})
    assert [len(p) for p in geo['coordinates']] == [2, 1]


def test_geocode_ranks_exact_then_partial_and_prefers_parcels(use_store):
    from api.main import pickering_geocode
    candidates = pickering_geocode('test st')['candidates']
    assert [c['label'] for c in candidates] == ['1 Test St', '3 Test St']
    assert pickering_geocode('1801000002')['candidates'][0]['label'] == '1801000002'
    assert pickering_geocode('zzz')['candidates'] == []


def test_map_returns_the_lot_and_layers_in_wgs84(use_store):
    from api.main import pickering_map
    result = pickering_map(LAT, LON, radius_m=300)
    assert result['parcel']['properties']['ADDRESS'] == '1 Test St'
    ring = result['parcel']['geometry']['coordinates'][0][0]
    assert all(abs(x - LON) < 0.001 and abs(y - LAT) < 0.001 for x, y in ring)
    layers = {l['category']: l for l in result['layers']}
    assert set(layers) == {'parcels', 'zoning', 'rail', 'official_plan'}
    assert {f['properties']['_zone'] for f in layers['zoning']['features']['features']} == {'R4', 'R3-7'}
    assert pickering_map(LAT, LON, radius_m=25)['layers'][-1]['category'] != 'rail'  # rail is ~190 m away
    json.dumps(result)


def test_documents_are_grouped_searchable_and_served(use_store):
    from fastapi import HTTPException
    from api.main import pickering_document_file, pickering_documents, pickering_search
    docs = pickering_documents()
    bylaw = docs['groups']['zoning_bylaw'][0]
    assert bylaw['pages'] == 2
    hits = pickering_search('lot frontage')['results']
    assert hits[0]['page'] == 2 and 'R4 zone' in hits[0]['snippet']
    response = pickering_document_file(bylaw['file'])
    assert response.media_type == 'application/pdf'
    for bad in ('manifest.json', '../../etc/passwd', 'catalog.json'):
        with pytest.raises(HTTPException):
            pickering_document_file(bad)


def test_lookup_quotes_the_zone_text(use_store):
    refs = zoning_lookup(CITY, LAT, LON)['steps']['6_planning_frameworks']
    excerpt = refs['zoning_bylaw_references'][0]['excerpts'][0]
    assert excerpt['page'] == 2 and 'minimum lot frontage' in excerpt['text']
    assert 'zoning_bylaw' in refs['all_documents']


@pytest.mark.skipif(__import__('shutil').which('tesseract') is None, reason='Tesseract not installed')
def test_scanned_bylaw_pages_are_read_with_ocr(tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.utils import ImageReader
    from scripts.scrape_pickering_zoning import pdf_pages
    image = Image.new('RGB', (1700, 300), 'white')
    try:
        font = ImageFont.truetype('DejaVuSans.ttf', 64)
    except OSError:
        font = ImageFont.load_default(size=64)
    ImageDraw.Draw(image).text((40, 100), 'R4 ZONE FRONTAGE 15 METRES', fill='black', font=font)
    path = tmp_path / 'scanned.pdf'
    pdf = canvas.Canvas(str(path))
    pdf.drawImage(ImageReader(image), 20, 500, width=560, height=99)
    pdf.save()
    text, ocr_pages = pdf_pages(path)
    assert ocr_pages == [0] and 'FRONTAGE' in text[0].upper()
    assert pdf_pages(path, ocr=False) == ([''], [])


def test_zone_standards_and_neighbours(use_store):
    steps = zoning_lookup(CITY, LAT, LON)['steps']
    assert steps['2_existing_zoning_and_official_plan']['zone_codes'] == ['R4']
    assert steps['4_site_characteristics']['adjacent_zone_codes'] == ['R3-7']
    standards = steps['3_proposed_development']['zone_standards_in_bylaw_text']
    assert standards['lot_frontage'][0]['bound'] == 'minimum' and standards['lot_frontage'][0]['measures'] == ['15 m']
    assert standards['building_height'][0]['bound'] == 'maximum' and standards['building_height'][0]['page'] == 2
    assert standards['rear_yard'][0]['measures'] == ['7.5 metres']
    assert 'detached dwelling' in standards['permitted_uses'][0]['text']
    assert standards['parking'] == []  # mentioned without a measure, so not a standard


def test_exception_zones_search_their_parent_zone():
    from engine.pickering_zoning import zone_variants
    assert zone_variants(['R4-12', 'MU(SA)', 'A']) == ['R4-12', 'R4', 'MU(SA)', 'MU', 'A']


def test_regional_layers_are_clipped_to_pickering(store):
    out, manifest = store
    regional = [l for l in manifest['layers'] if l['source'] == 'Region']
    assert [(l['name'], l['category'], l['features']) for l in regional] == \
        [('Map 1 - Regional Centres', 'official_plan', 1)]  # Oshawa left out; the empty Moraine layer skipped
    assert not manifest['completeness']['not_downloaded']


def test_regional_plan_shows_in_the_lot_review(use_store):
    plan = zoning_lookup(CITY, LAT, LON)['steps']['2_existing_zoning_and_official_plan']['official_plan']
    assert plan[0]['attributes']['Name'] == 'Pickering City Centre'
