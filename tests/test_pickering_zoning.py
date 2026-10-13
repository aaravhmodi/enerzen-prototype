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
         'geometry': {'rings': [square(LON, LAT, 0.002)]}}]),
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


def bylaw_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, 'Zoning By-law 3036 general provisions')
    pdf.showPage()
    pdf.drawString(72, 720, 'Section 5: R4 zone - minimum lot frontage 15 m')
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
            wanted = {int(i) for i in q['objectIds'].split(',')}
            return self.send({'features': [f for f in features if f['attributes']['OBJECTID'] in wanted]})
        if path == '/site/zoning/':
            return self.send(b'<html><title>Zoning | Pickering</title><a href="/files/by-law-3036.pdf">Zoning '
                             b'By-law 3036</a><a href="/files/menu.pdf">Recreation guide</a>'
                             b'<a href="/site/official-plan/">Official Plan</a><a href="/site/parks/">Parks</a>',
                             'text/html')
        if path == '/site/official-plan/':
            return self.send(b'<html><title>Official Plan</title></html>', 'text/html')
        if path == '/files/by-law-3036.pdf':
            return self.send(self.pdf, 'application/pdf')
        self.send_response(404)
        self.end_headers()


@pytest.fixture(scope='module')
def store(tmp_path_factory):
    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeCity)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = f'http://127.0.0.1:{server.server_port}'
    out = tmp_path_factory.mktemp('pickering')
    manifest = scrape(out, arcgis_roots=[f'{host}/arcgis/rest/services'],
                      document_pages=[f'{host}/site/zoning/', f'{host}/site/missing/'],
                      fetch=Fetcher(delay=0, retries=1), log=lambda *_: None)
    server.shutdown()
    return out, manifest


@pytest.fixture
def use_store(store, monkeypatch):
    monkeypatch.setenv('PICKERING_DATA_DIR', str(store[0]))
    return store


def test_scrape_downloads_matched_layers_and_relevant_documents(store):
    out, manifest = store
    assert {layer['category'] for layer in manifest['layers']} == {'zoning', 'parcels', 'rail'}
    assert len(json.loads((out / 'catalog.json').read_text())) == 4  # footprints catalogued, not downloaded
    docs = {d['url'].rsplit('/', 2)[-2] + '/' + d['url'].rsplit('/', 1)[-1]: d for d in manifest['documents']}
    assert 'files/by-law-3036.pdf' in docs and docs['files/by-law-3036.pdf']['pages'] == 2
    assert 'files/menu.pdf' not in docs and not any('parks' in u for u in docs)
    assert [e['url'].endswith('/site/missing/') for e in manifest['errors']] == [True]


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
    assert set(layers) == {'parcels', 'zoning', 'rail'}
    assert layers['zoning']['features']['features'][0]['properties']['_zone'] == 'R4'
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
