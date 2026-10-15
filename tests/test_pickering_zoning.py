"""Scrape a fake Pickering ArcGIS server and website, then look parcels up from the store."""
import io
import json
import threading
from pathlib import Path
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
        {'attributes': {'OBJECTID': 8, 'ADDRESS': '3 Test St', 'ROLL_NUM': '1801000002', 'LEGAL': 'PART LOT 17 CONCESSION 8'},
         'geometry': {'rings': [square(LON + 0.001, LAT, 0.0003)]}}]),
    2: ('CN Railway', 'esriGeometryPolyline', [
        {'attributes': {'OBJECTID': 1, 'OWNER': 'CN'},
         'geometry': {'paths': [[[LON - 0.01, LAT + 0.002], [LON + 0.01, LAT + 0.002]]]}}]),
    3: ('Building Footprints', 'esriGeometryPolygon', []),
    5: ('Street Centreline', 'esriGeometryPolyline', [
        {'attributes': {'OBJECTID': 1, 'STREET': 'Test St'},
         'geometry': {'paths': [[[LON - 0.003, LAT - 0.0004], [LON + 0.003, LAT - 0.0004]]]}},
        {'attributes': {'OBJECTID': 2, 'STREET': 'Corner Ave'},  # 1 Test St is a corner lot
         'geometry': {'paths': [[[LON + 0.00045, LAT - 0.003], [LON + 0.00045, LAT + 0.003]]]}}]),
}


REGION_FEATURES = [  # one centre in Pickering, one in Oshawa (outside the clip)
    {'attributes': {'OBJECTID': 1, 'Name': 'Pickering City Centre'}, 'geometry': {'rings': [square(LON, LAT, 0.004)]}},
    {'attributes': {'OBJECTID': 2, 'Name': 'Oshawa Centre'}, 'geometry': {'rings': [square(-78.86, 43.90, 0.004)]}},
]


def text_pdf(*lines) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for i, line in enumerate(lines):
        pdf.drawString(72, 720 - 20 * i, line)
    pdf.save()
    return buffer.getvalue()


AMENDMENT = text_pdf('The Corporation of the City of Pickering By-law No. 8276/26',
                     'Being a by-law to amend Zoning By-law 8149/24', 'Schedule 1 is amended from A to R4-X5',
                     'for lands in Part of Lot 5, Plan 40M-1 and Lots 17 and 18, Concession 8',
                     'X 5', 'The minimum front yard shall be 4.5 metres')
PARKING = text_pdf('The Corporation of the City of Pickering By-law No. 8300/26', 'Being a by-law respecting parking fines')


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
    # The zone table the per-lot setbacks come from.
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    table = Table([['Requirement', 'R3', 'R4'], ['Minimum Lot Frontage', '18.0 m', '15.0 m'],
                   ['Minimum Lot Area', '550 m2', '460 m2'], ['Minimum Front Yard', '7.5 m', '6.0 m'],
                   ['Minimum Interior Side Yard', '1.5 m', '1.2 m'], ['Minimum Exterior Side Yard', '4.5 m', '4.5 m'],
                   ['Minimum Rear Yard', '7.5 m', '7.5 m'], ['Maximum Lot Coverage', '33%', '38%'],
                   ['Maximum Building Height', '9.0 m', '9.0 m']])
    table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    table.wrapOn(pdf, 400, 300)
    table.drawOn(pdf, 72, 400)
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
        body = self.rfile.read(length).decode()
        if self.path.endswith('/GetCalendarMeetings'):
            assert json.loads(body)['calendarStartDate'] == '2024-12-01'
            # As the City's eScribe answers: a Url that 404s, so the agenda page is built from the ID.
            return self.send({'d': [{'ID': 'm1', 'Url': f'http://{self.headers["Host"]}/escribe/MeetingsCalendarView.aspx/Meeting?Id=m1'},
                                    {'ID': 'm1', 'Url': f'http://{self.headers["Host"]}/escribe/MeetingsCalendarView.aspx/Meeting?Id=m1'}]})
        self.route(parse_qs(body))

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
        if path == '/wayback/cdx/search/cdx':  # the Wayback Machine has the withdrawn draft, not the missing page
            header = ['urlkey', 'timestamp', 'original', 'mimetype', 'statuscode', 'digest', 'length']
            kept = [['k', '20241202075255', q['url'], 'application/pdf', '200', 'd', '1']] if q['url'].endswith('/withdrawn.pdf') else []
            return self.send([header, *kept])
        if path.startswith('/wayback/web/20241202075255id_/'):
            return self.send(self.pdf, 'application/pdf')
        if path == '/escribe/Meeting.aspx':
            return self.send(b'<a href="FileStream.ashx?DocumentId=1">By-law 8276/26</a>'
                             b'<a href="FileStream.ashx?DocumentId=2">By-law 8300/26</a>'
                             b'<a href="FileStream.ashx?DocumentId=3">Staff Report PLN 01-26</a>', 'text/html')
        if path == '/escribe/FileStream.ashx':
            assert q['DocumentId'] != '3', 'only by-laws are downloaded'
            return self.send(AMENDMENT if q['DocumentId'] == '1' else PARKING, 'application/pdf')
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
                      document_pages=[f'{host}/site/zoning/', f'{host}/site/missing/', f'{host}/files/withdrawn.pdf'],
                      fetch=Fetcher(delay=0, retries=1), log=lambda *_: None, escribe=f'{host}/escribe',
                      archive=f'{host}/wayback')
    server.shutdown()
    return out, manifest


@pytest.fixture
def use_store(store, monkeypatch):
    monkeypatch.setenv('PICKERING_DATA_DIR', str(store[0]))
    return store


def test_scrape_downloads_every_layer_and_proves_it(store):
    out, manifest = store
    assert {layer['category'] for layer in manifest['layers']} == {'zoning', 'parcels', 'rail', 'official_plan', 'roads'}  # empty footprints skipped
    assert len(json.loads((out / 'catalog.json').read_text())) == 7
    parcels = next(l for l in manifest['layers'] if l['category'] == 'parcels')
    assert parcels['features'] == parcels['expected'] == 2 and parcels['complete']  # the capped page was retried
    report = manifest['completeness']
    assert report['cited_bylaws'] == ['2511', '3036', '9999/21'] and report['missing_bylaws'] == ['9999/21']
    assert report['superseded_bylaws_cited'] == 2  # the parent by-laws 8149/24 replaced need no copy of their own
    assert not report['incomplete_layers'] and not report['not_downloaded']
    assert report['complete'] is False  # the missing by-law and the dead page keep it honest


def test_scrape_follows_listing_pages_and_takes_every_pdf_on_planning_pages(store):
    _, manifest = store
    docs = {d['url'].split('/', 3)[-1]: d for d in manifest['documents']}
    assert docs['files/by-law-3036.pdf']['pages'] == 2
    assert {'files/2511.pdf', 'files/menu.pdf', 'site/zoning/?page=2', 'site/official-plan/'} <= set(docs)
    assert not any('parks' in u for u in docs)
    assert [e['url'].endswith('/site/missing/') for e in manifest['errors']] == [True]
    # A document the City has taken down comes from the Wayback Machine's copy, which is recorded.
    assert docs['files/withdrawn.pdf']['pages'] == 2
    assert docs['files/withdrawn.pdf']['archived_copy'].endswith('/wayback/web/20241202075255id_/' + docs['files/withdrawn.pdf']['url'])


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
           fetch=Fetcher(delay=0, retries=1, timeout=2), log=lambda *_: None, escribe=None)
    assert (out / 'manifest.json').read_text() == before
    # The map server answers but the by-law's own text cannot be had (its records server is down): every
    # layer arrives, no zone standards are read, and the working copy is still kept.
    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeCity)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        run = scrape(out, arcgis_roots=[f'http://127.0.0.1:{server.server_port}/arcgis/rest/services'], document_pages=[],
                     fetch=Fetcher(delay=0, retries=1), log=lambda *_: None, escribe=None, archive=None)
    finally:
        server.shutdown()
    assert run['layers'] and not run['promoted'] and (out / 'manifest.json').read_text() == before
    # A document the City cannot serve this time (its server is gone) keeps the last good run's copy,
    # with the date that copy was fetched, and the failure is still on record.
    from scripts.scrape_pickering_zoning import collect_documents
    entry = next(d for d in store[1]['documents'] if d['url'].endswith('/files/by-law-3036.pdf'))
    errors = []
    docs = collect_documents(Fetcher(delay=0, retries=1, timeout=2), out, [entry['url']], errors, archive=None,
                             docs_dir=out / 'snapshots' / 'next' / 'documents',
                             kept={entry['url']: {'carried_over_from': '2026-10-13', **entry}})
    assert [d['carried_over_from'] for d in docs] == ['2026-10-13'] and [e['url'] for e in errors] == [entry['url']]
    assert Path(docs[0]['file']).parts[:3] == ('snapshots', 'next', 'documents')
    assert (out / docs[0]['file']).read_bytes() == (out / entry['file']).read_bytes() and (out / docs[0]['text_file']).exists()


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
    assert classify('Street Centreline') == 'roads'
    assert classify('Building Footprints') is None
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
    assert set(layers) == {'parcels', 'zoning', 'rail', 'official_plan', 'roads'}
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
    assert zone_variants(['R4 (X12)', 'C1-X3(H)']) == ['R4 (X12)', 'R4', 'X12', 'C1-X3(H)', 'C1', 'X3']


def test_regional_layers_are_clipped_to_pickering(store):
    out, manifest = store
    regional = [l for l in manifest['layers'] if l['source'] == 'Region']
    assert [(l['name'], l['category'], l['features']) for l in regional] == \
        [('Map 1 - Regional Centres', 'official_plan', 1)]  # Oshawa left out; the empty Moraine layer skipped
    assert not manifest['completeness']['not_downloaded']


def test_regional_plan_shows_in_the_lot_review(use_store):
    plan = zoning_lookup(CITY, LAT, LON)['steps']['2_existing_zoning_and_official_plan']['official_plan']
    assert plan[0]['attributes']['Name'] == 'Pickering City Centre'


def test_council_zoning_amendments_are_kept_and_others_dropped(store):
    out, manifest = store
    council = [d for d in manifest['documents'] if d.get('source') == 'council']
    assert [d['title'] for d in council] == ['Zoning amendment By-law 8276/26']
    assert len(list((out / manifest['snapshot'] / 'documents' / 'council').glob('*.pdf'))) == 1


def test_amendments_and_exception_zones_reach_the_lot_review(use_store):
    from api.main import pickering_search
    hits = pickering_search('R4-X5')['results']
    assert hits[0]['title'] == 'Zoning amendment By-law 8276/26' and hits[0]['group'] == 'zoning_bylaw'


def test_lot_review_lists_amendments_naming_the_lot(use_store):
    from engine.pickering_zoning import _lot_concession
    assert _lot_concession('Part of Lots 17 and 18, Concession 8') == {('17', '8'), ('18', '8')}
    assert _lot_concession('PT LT 22 CON 4') == set()  # abbreviations without "Lot" are not guessed
    amendments = zoning_lookup(CITY, LAT, LON)['steps']['6_planning_frameworks']['council_amendments_naming_this_lot']
    assert amendments == []  # the lot is "LOT 5 PLAN 40M-1", not a lot and concession
    neighbour = zoning_lookup(CITY, LAT, LON + 0.001)['steps']['6_planning_frameworks']
    assert [(a['title'], a['reasons']) for a in neighbour['council_amendments_naming_this_lot']] == \
        [('Zoning amendment By-law 8276/26', ['names Lot 17, Concession 8'])]
    status = pickering_data_status()
    assert status['council_amendments'] == 1 and status['completeness']['missing_bylaws'] == ['9999/21']


def test_lot_dimensions_and_street_side_for_the_site_planner(use_store):
    result = zoning_lookup(CITY, LAT, LON)
    dims = result['steps']['1_property_identification']['from_city_data']['dimensions']
    assert dims['width_m'] == pytest.approx(48.2, abs=0.5) and dims['depth_m'] == pytest.approx(66.7, abs=0.5)
    assert dims['street_side'] == 'S' and dims['rectangularity'] == 1.0
    assert result['parcel'] == {'address': '1 Test St', 'zoning': 'R4', 'by_law': '3036',
                                'official_plan': 'Pickering City Centre', 'overlays': 'rail',
                                'lot': f"{dims['width_m']} m × {dims['depth_m']} m",
                                'setbacks': 'front 6 m (S), rear 7.5 m (N), exterior side 4.5 m (E), '
                                            'interior side 1.2 m (W)'}


def test_rotated_lot_reports_its_own_sides():
    from shapely import affinity
    from shapely.geometry import LineString, box
    from engine.pickering_zoning import lot_dimensions
    lot = affinity.rotate(box(0, 0, 15, 40), 20, origin='centroid')  # 15 m frontage, 40 m deep, turned 20 degrees
    dims = lot_dimensions(lot, [LineString([(-50, 60), (50, 60)])])
    assert (dims['width_m'], dims['depth_m'], dims['rotation_deg']) == (15.0, 40.0, 20.0)
    assert dims['street_side'] == 'N'


def test_feasibility_names_the_lot_zone_but_never_passes_it(use_store):
    from engine import feasibility as fz
    parcel = zoning_lookup(CITY, LAT, LON)['parcel']
    check = fz.zoning_check(CITY, parcel)
    assert check.status == fz.NOT_CHECKED
    assert check.detail.startswith('1 Test St is zoned R4 (by-law 3036); Official Plan: Pickering City Centre')
    assert fz.zoning_check(CITY, {}).detail.startswith('No Pickering parcel')


def test_every_setback_of_a_corner_lot_comes_from_the_bylaw(use_store):
    standards = zoning_lookup(CITY, LAT, LON)['steps']['3_proposed_development']['lot_standards']
    assert (standards['zone'], standards['street_side'], standards['flank_side'], standards['corner_lot']) == \
        ('R4', 'S', 'E', True)
    by_side = {side: (v['applies'], v['value']) for side, v in standards['setbacks_by_side'].items()}
    assert by_side == {'S': ('front_yard', 6.0), 'N': ('rear_yard', 7.5), 'E': ('exterior_side_yard', 4.5),
                       'W': ('interior_side_yard', 1.2)}
    front = standards['setbacks_by_side']['S']
    assert front['from'] == 'Zone R4 table' and front['page'] == 2 and 'by-law-3036' in front.get('label', '') + str(
        standards['standards']['front_yard']['file'])
    assert standards['complete'] and standards['missing'] == ['landscaped_area']
    assert [(c['standard'], c['ok']) for c in standards['lot_checks']] == [('lot_frontage', True), ('lot_area', True)]
    # 48.2 x 66.7 m lot less 4.5 + 1.2 m sides and 6 + 7.5 m front and rear
    assert standards['buildable_area_m2'] == pytest.approx((48.2 - 5.7) * (66.7 - 13.5), rel=0.02)
    assert standards['max_coverage_m2'] == pytest.approx(0.38 * 48.2 * 66.7, rel=0.02)


def test_an_exception_overrides_its_zone_and_says_so(use_store):
    from engine import lot_rules
    from engine.pickering_zoning import zone_rules
    resolved = lot_rules.resolve('R4-X5', zone_rules())
    assert resolved['front_yard']['value'] == 4.5 and resolved['front_yard']['from'] == 'Exception X5'
    assert resolved['front_yard']['overrides'] == 6.0 and resolved['rear_yard']['from'] == 'Zone R4 table'
    unknown = lot_rules.apply_to_lot(None, 'ZZ9', zone_rules(), [], None)
    assert unknown['missing'][:3] == ['front_yard', 'rear_yard', 'interior_side_yard'] and not unknown['complete']


def test_every_stored_lot_gets_its_setbacks(use_store):
    from api.main import pickering_setbacks_coverage, pickering_setbacks_csv
    from engine.pickering_zoning import all_lots
    rows = {r['address']: r for r in all_lots()}
    corner = rows['1 Test St']
    assert (corner['zone'], corner['front_yard_m'], corner['rear_yard_m'], corner['interior_side_yard_m'],
            corner['exterior_side_yard_m'], corner['corner_lot'], corner['complete']) == ('R4', 6.0, 7.5, 1.2, 4.5, True, True)
    assert 'Zone R4 table p.2' in corner['sources']
    neighbour = rows['3 Test St']  # inside the R3-7 polygon: R3 standards, exception 7 has no stored section
    assert neighbour['zone'] in ('R3', 'R4') and neighbour['street_side'] == 'S'
    coverage = pickering_setbacks_coverage()
    assert coverage['lots'] == 2 and coverage['complete'] == 2 and coverage['corner_lots'] == 1
    csv_text = pickering_setbacks_csv().body.decode()
    assert csv_text.splitlines()[0].startswith('address,roll_number,pin') and '1 Test St' in csv_text


def test_zone_code_joins_the_exception_field_and_ignores_overlays():
    # The City's zoning layer keeps the exception number in its own field.
    assert pickering_zoning._zone_code({'ZONING_CODE': 'R1G', 'EXCEPTION_NUM': '146'}) == 'R1G-X146'
    assert pickering_zoning._zone_code({'ZONING_CODE': 'A', 'EXCEPTION_NUM': None}) == 'A'
    assert pickering_zoning._zone_code({'IPZ_ID': 3, 'IPZType': 'IPZ-1'}) is None  # Intake Protection Zones


def test_lookup_takes_the_lot_not_a_larger_parcel_around_it(use_store):
    # The City publishes its own outline as a one-feature "parcel" layer that contains every lot.
    manifest, layers = pickering_zoning.load_store()
    lots = next(l for l in layers if l.meta['category'] == 'parcels')
    attrs, geom = next(f for f in lots.features if f[1] is not None)
    outline = pickering_zoning.Layer.__new__(pickering_zoning.Layer)
    outline.meta = {**lots.meta, 'name': 'City outline'}
    outline.features, outline._indexed = [({'NAME': 'Pickering'}, geom.buffer(5000))], [0]
    outline.tree = pickering_zoning.STRtree([outline.features[0][1]])
    layers.insert(0, outline)
    try:
        point = geom.representative_point()
        found = pickering_zoning.lookup(point.y / pickering_zoning.M_PER_DEG_LAT, point.x / pickering_zoning.M_PER_DEG_LON)
        assert found['steps']['1_property_identification']['from_city_data']['area_m2'] == round(geom.area, 1)
    finally:
        layers.remove(outline)


def test_a_lot_at_an_angle_fronts_on_its_street_side():
    # 1025 Dalewood Dr: 16.5 m on the street and 33 m deep, turned 37 degrees from north. Its long
    # side was taken as the frontage, which left a 4.5 m strip to build on.
    from shapely import affinity
    from shapely.geometry import LineString, box
    from engine import lot_rules
    lot = affinity.rotate(box(0, 0, 16.5, 33), -37, origin=(0, 0))
    street = affinity.rotate(LineString([(-50, -10), (60, -10)]), -37, origin=(0, 0))
    dims = pickering_zoning.lot_dimensions(lot, [street])
    assert (dims['width_m'], dims['depth_m'], dims['street_side']) == (16.5, 33.0, 'S')
    yard = lambda value: {'value': value, 'unit': 'm'}
    rules = {'zones': {'R1G': {'front_yard': yard(4.5), 'rear_yard': yard(7.5), 'interior_side_yard': yard(1.2)}},
             'exceptions': {}}
    found = lot_rules.apply_to_lot(lot, 'R1G', rules, [street], dims)
    assert found['setbacks_by_side']['S']['applies'] == 'front_yard' and not found['corner_lot']
    assert found['buildable_area_m2'] == pytest.approx((16.5 - 2.4) * (33 - 12), abs=0.5)


def test_a_corner_lot_fronts_on_its_shorter_street_line():
    # By-law 8149/24, "Lot Line, Front". 1154 Meadowlane Cres got its front yard along its 33.6 m side.
    from shapely.geometry import LineString, box
    from engine import lot_rules
    lot = box(0, 0, 36, 18)
    long_street, short_street = LineString([(-40, -8), (80, -8)]), LineString([(-9, -40), (-9, 60)])
    dims = pickering_zoning.lot_dimensions(lot, [long_street, short_street])
    yard = lambda value: {'value': value, 'unit': 'm'}
    rules = {'zones': {'R1F': {'front_yard': yard(4.5), 'rear_yard': yard(7.5), 'interior_side_yard': yard(1.2),
                               'exterior_side_yard': yard(2.7)}}, 'exceptions': {}}
    found = lot_rules.apply_to_lot(lot, 'R1F', rules, [long_street, short_street], dims)
    assert {side: v['applies'] for side, v in found['setbacks_by_side'].items()} == {
        'W': 'front_yard', 'E': 'rear_yard', 'S': 'exterior_side_yard', 'N': 'interior_side_yard'}
    assert found['corner_lot'] and found['buildable_area_m2'] == pytest.approx((36 - 12) * (18 - 3.9), abs=0.5)


def test_a_townhouse_on_a_rear_lane_fronts_its_street_and_has_no_yard_at_its_common_walls():
    # 2670 Castlegate Crossing: 4.5 m wide, a street in front, Four Seasons Lane behind, and the City's
    # footprint of the whole townhouse block running across both side lot lines.
    from shapely.geometry import LineString, box
    from engine import lot_rules
    lot, block = box(0, 0, 4.5, 26), box(-9, 6, 13.5, 18)
    street, lane = LineString([(-40, -9), (40, -9)]), LineString([(-40, 30), (40, 30)])  # the lane is the nearer
    dims = pickering_zoning.lot_dimensions(lot, [street])
    attached = lot_rules.attached_sides(lot, dims['rotation_deg'], [block])
    assert attached == ['E', 'W'] and lot_rules.attached_sides(lot, 0, [box(0.2, 6, 4.5, 18)]) == []  # touching is not joined
    yard = lambda value, **more: {'value': value, 'unit': 'm', **more}
    kinds = [{'type': kind, 'provisions': {'lot_frontage': yard(4.5), 'front_yard': yard(3.0), 'rear_yard': yard(rear),
                                           'interior_side_yard': yard(1.5, common_wall='No side yard at a common wall.')}}
             for kind, rear in (('Street townhouse dwelling', 7.0), ('Integrated garage at the rear of the dwelling', 6.0))]
    rules = {'zones': {}, 'exceptions': {'X321': {'provisions': {}, 'by_lot_type': {'MU-MD-3': kinds}}}}
    found = lot_rules.apply_to_lot(lot, 'MU-MD-3-X321', rules, [street], dims, [lane], attached)
    sides = found['setbacks_by_side']
    assert found['street_side'] == 'S' and found['lane_lot'] and sides['N']['value'] == 6.0  # the lane kind's rear yard
    assert (sides['E']['value'], sides['E']['stated'], sides['W']['value']) == (0.0, 1.5, 0.0)
    assert found['buildable_area_m2'] == pytest.approx(4.5 * (26 - 3 - 6), abs=0.5)
    alone = lot_rules.apply_to_lot(lot, 'MU-MD-3-X321', rules, [street], dims, [], [])
    assert alone['setbacks_by_side']['N']['value'] == 7.0 and alone['setbacks_by_side']['E']['value'] == 1.5
    assert pickering_zoning._is_lane({'NAME': 'Four Seasons', 'SUFFIX': 'Lane'}) and not pickering_zoning._is_lane({'NAME': 'Lane', 'SUFFIX': 'Road'})


def test_a_side_yard_that_differs_from_one_side_to_the_other():
    # R1C: "One side 1.8 m and other side 3.0 m". Both figures are applied; which side is which is not known.
    from shapely.geometry import LineString, box
    from engine import lot_rules
    lot, street = box(0, 0, 21, 36), LineString([(-40, -9), (60, -9)])
    dims = pickering_zoning.lot_dimensions(lot, [street])
    yard = lambda value, **more: {'value': value, 'unit': 'm', **more}
    rules = {'zones': {'R1C': {'front_yard': yard(9.0), 'rear_yard': yard(7.5), 'interior_side_yard': yard(1.8, other_side=3.0)}},
             'exceptions': {}}
    found = lot_rules.apply_to_lot(lot, 'R1C', rules, [street], dims)
    assert sorted(found['setbacks_by_side'][side]['value'] for side in 'EW') == [1.8, 3.0]
    assert found['buildable_area_m2'] == pytest.approx((21 - 4.8) * (36 - 16.5), abs=0.5)


def test_city_centre_lots_and_lots_whose_setbacks_are_drawn():
    from shapely.geometry import LineString, box
    from engine import lot_rules
    lot, street = box(0, 0, 20, 30), LineString([(-40, -9), (60, -9)])
    dims = pickering_zoning.lot_dimensions(lot, [street])
    line = {'value': 1.0, 'unit': None, 'page': 118, 'document': 'By-law 8149/24', 'label': 'Minimum Building Setback from Street Line (m)'}
    drawn = {'text': 'Buildings and structures shall be located entirely within the building envelope shown on Figure 1', 'page': 407}
    rules = {'zones': {'CC*': {'street_line_setback': line}}, 'families': {'CC*': ['CC1', 'CC2', 'CCR1', 'CCR2']},
             'exceptions': {'X103': {'provisions': {}, 'zone_sections': ['RH-MU-2', 'MD-H6'], 'by_figure': {'RH-MU-2': drawn},
                                     'by_zone': {'MD-H6': {'front_yard': {'value': 3.0, 'unit': 'm'}}}}}}
    # By-law 8149/24, Table 8.6: 1.0 m from the street line, and no side or rear yard.
    for code in ('CCR2', 'CC 2-X387', 'CC Res 1-X386'):
        found = lot_rules.apply_to_lot(lot, code, rules, [street], dims)
        assert {s: v['value'] for s, v in found['setbacks_by_side'].items()} == {'S': 1.0, 'N': 0.0, 'E': 0.0, 'W': 0.0}, code
        assert found['complete'] and found['basis'] == 'street_line' and found['basis_page'] == 118 and not found['missing'][:1] == ['front_yard']
    assert lot_rules.apply_to_lot(lot, 'CCA-2-X221', rules, [street], dims)['basis'] == 'none_stated'  # not a City Centre zone
    # Exception 103: the RH-MU-2 zone's buildings go inside an envelope drawn on Figure 1.
    found = lot_rules.apply_to_lot(lot, 'RH-MU-2-X103', rules, [street], dims)
    assert not found['complete'] and found['basis'] == 'figure' and found['basis_page'] == 407 and 'Figure 1' in found['basis_note']
    assert lot_rules.apply_to_lot(lot, 'MD-H6-X103', rules, [street], dims)['basis'] == 'partial'  # its own section, no drawing
    assert lot_rules.apply_to_lot(lot, None, rules, [street], dims)['basis'] == 'no_zone'
    # The figure's distances, read off the drawing, come with the lot, feet turned to metres.
    rules['exceptions']['X103']['figures'] = [{'figure': 'Figure 1', 'document': 'Exception Zones X1 to X215', 'page': 415,
                                              'unit': 'ft', 'setbacks': [['Bayly Street', 20]]}]
    drawn_figure = lot_rules.apply_to_lot(lot, 'RH-MU-2-X103', rules, [street], dims)['figure_setbacks']
    assert drawn_figure[0]['page'] == 415 and drawn_figure[0]['setbacks'] == [{'from': 'Bayly Street', 'value_m': 6.1, 'stated': '20 ft'}]
    # A figure that is a table of yards by zone gives the lot its yards, cited to the figure.
    rules['exceptions']['X295'] = {'provisions': {}, 'figures': [{
        'figure': 'Figure 1', 'document': 'Exception Zones X216 to X437', 'page': 374, 'unit': 'm', 'setbacks': [],
        'yards': {'S1': {'front_yard': 4.5, 'interior_side_yard': 1.2, 'exterior_side_yard': 2.7, 'rear_yard': 7.5}}}]}
    found = lot_rules.apply_to_lot(lot, 'S1-X295', rules, [street], dims)
    assert {s: v['value'] for s, v in found['setbacks_by_side'].items()} == {'S': 4.5, 'N': 7.5, 'E': 1.2, 'W': 1.2}
    assert found['basis'] == 'yards' and found['standards']['front_yard']['from'] == 'Exception X295, Figure 1'


def test_urban_reserve_lots_and_figures_that_set_some_lots_apart():
    from shapely.geometry import LineString, box
    from engine import lot_rules
    lot, street = box(0, 0, 20, 30), LineString([(-40, -9), (60, -9)])
    dims = pickering_zoning.lot_dimensions(lot, [street])
    yard = lambda value, **more: {'value': value, 'unit': 'm', **more}
    rules = {'zones': {'A': {'front_yard': yard(12.0), 'rear_yard': yard(12.0), 'interior_side_yard': yard(3.0)}, 'UT': {}},
             'exceptions': {'X266': {'provisions': {'front_yard': yard(4.5, varies='for lots fronting on Fairport Road: 7.5 metres for all other lots: 4.5 metres'),
                                                    'rear_yard': yard(7.5), 'interior_side_yard': yard(1.2)}}}}
    # By-law 8149/24, Table 13.3, note 1: the UR zone takes the Agriculture zone's requirements.
    found = lot_rules.apply_to_lot(lot, 'UR', rules, [street], dims)
    assert found['complete'] and found['setbacks_by_side']['S']['value'] == 12.0 and 'Table 13.3' in found['setbacks_by_side']['S']['from']
    assert lot_rules.apply_to_lot(lot, 'UT', rules, [street], dims)['basis'] == 'none_stated'
    found = lot_rules.apply_to_lot(lot, 'S3-7-X266', rules, [street], dims)['setbacks_by_side']
    assert found['S']['value'] == 4.5 and 'Fairport Road' in found['S']['note'] and 'note' not in found['N']


def test_a_lot_takes_the_figures_for_its_own_kind_of_dwelling_and_its_own_size():
    from shapely.geometry import LineString, box
    from engine import lot_rules
    lot, street = box(0, 0, 20, 30), LineString([(-40, -9), (60, -9)])
    dims = pickering_zoning.lot_dimensions(lot, [street])
    yard = lambda value, **more: {'value': value, 'unit': 'm', **more}
    side = yard(1.2, other_side=0.0, kind='detached dwellings', common_wall='no interior side yard along a common wall',
                other_kinds=[yard(0.6, kind='semi detached dwellings')])
    rules = {'zones': {'ORMA': {'front_yard': {'value': 15.0, 'unit': None, 'small_lot': {'below_ha': 4.0, 'value': 12.0}},
                                'rear_yard': yard(15.0), 'interior_side_yard': yard(6.0)}},
             'exceptions': {'X151': {'provisions': {'front_yard': yard(3.0), 'rear_yard': yard(7.5), 'interior_side_yard': side}}}}
    sides = lambda **more: {s: v['value'] for s, v in lot_rules.apply_to_lot(lot, 'S2-X151', rules, [street], dims, **more)['setbacks_by_side'].items()}
    assert sides() == {'S': 3.0, 'N': 7.5, 'E': 1.2, 'W': 0.0}  # detached: 1.2 one side, no minimum the other
    assert sides(attached=['W']) == {'S': 3.0, 'N': 7.5, 'E': 0.6, 'W': 0.0}  # semi-detached: 0.6, and none at the common wall
    found = lot_rules.apply_to_lot(lot, 'S2-X151', rules, [street], dims, attached=['W'])
    assert 'semi detached dwellings' in found['standards']['interior_side_yard']['from']
    # A 600 m2 lot in the ORMA zone is under four hectares.
    assert lot_rules.apply_to_lot(lot, 'ORMA', rules, [street], dims)['setbacks_by_side']['S']['value'] == 12.0
    big = box(0, 0, 300, 300)
    assert lot_rules.apply_to_lot(big, 'ORMA', rules, [street], pickering_zoning.lot_dimensions(big, [street]))['setbacks_by_side']['S']['value'] == 15.0


def test_a_parcel_without_a_legal_description_gets_one_from_the_city_layers():
    from shapely.geometry import box
    square = lambda: {'type': 'Polygon', 'coordinates': [[[-79.2, 43.8], [-79.0, 43.8], [-79.0, 43.9], [-79.2, 43.9], [-79.2, 43.8]]]}
    fabric = pickering_zoning.Layer({'name': 'Lot Fabric Improved', 'category': 'parcels'}, {'features': [
        {'properties': {'LOT_IDENT': 'LOT 27', 'CONCESSION_IDENT': 'CON 3', 'GEOGRAPHIC_TOWNSHIP_NAME': 'PICKERING'},
         'geometry': square()}]})
    plans = pickering_zoning.Layer({'name': 'Major Residential Developments', 'category': None}, {'features': [
        {'properties': {'PLAN_NO': '40M-2600', 'SUBDIVISIO': 'SP-2009-13'}, 'geometry': square()}]})
    x, y = -79.1 * pickering_zoning.SCALE[0], 43.85 * pickering_zoning.SCALE[1]
    lot = box(x - 5, y - 5, x + 5, y + 5)
    assert pickering_zoning._legal_description([fabric, plans], lot, {}) == (
        "Registered Plan 40M-2600; Part of Lot 27, Concession 3, Geographic Township of Pickering "
        "(from the City's subdivision and lot fabric layers)")
    assert pickering_zoning._legal_description([fabric, plans], lot, {'LEGAL_DESC': 'PLAN 40M-1 LOT 2'}) == 'PLAN 40M-1 LOT 2'


def test_council_by_laws_saved_from_a_browser_are_imported_like_scraped_ones(store, tmp_path):
    import base64
    import shutil
    from scripts.scrape_pickering_zoning import import_council
    out = tmp_path / 'copy'
    shutil.copytree(store[0], out)
    bundle = tmp_path / 'bundle.json'
    doc = lambda n, pdf: {'url': f'https://pub-pickering.escribemeetings.com/FileStream.ashx?DocumentId={n}',
                          'title': f'By-law {n}.pdf', 'meeting_url': 'https://pub-pickering.escribemeetings.com/Meeting.aspx?Id=m9',
                          'meeting_date': '2026/04/27', 'pdf_base64': base64.b64encode(pdf).decode()}
    bundle.write_text(json.dumps({'retrieved_at': '2026-10-14T20:49:00Z',
                                  'documents': [doc(9001, AMENDMENT), doc(9002, PARKING)]}), encoding='utf-8')
    added = import_council(out, bundle, ocr=False, log=lambda *_: None)
    assert [d['title'] for d in added] == ['Zoning amendment By-law 8276/26']  # the parking by-law is dropped
    manifest = json.loads((out / 'manifest.json').read_text())
    assert added[0]['url'] in {d['url'] for d in manifest['documents']} and added[0]['saved_from_browser'] == '2026-10-14T20:49:00Z'
    assert (out / added[0]['text_file']).exists()
    assert import_council(out, bundle, ocr=False, log=lambda *_: None) == []  # already in the store


def test_garden_suite_needs_a_permitting_zone_room_and_a_path(monkeypatch):
    from shapely.geometry import LineString, box
    from engine import pickering_zoning as pz
    lot, street = box(0, 0, 15, 40), LineString([(-50, -5), (50, -5)])
    monkeypatch.setattr(pz, '_streets_and_lanes', lambda *a: ([street], []))
    rules = {'additional_units': {
        'zones': {'R4': {'permitted': True, 'seaton': False, 'page': 98}, 'C1': {'permitted': False, 'seaton': False, 'page': 110}},
        'sections': {'4.3': {'large_lot_m2': 2000, 'max_height_m': 4.5, 'max_height_large_lot_m': 6.5,
                             'default_coverage_pct': 45, 'max_floor_area_m2': 150, 'path_width_m': 1.2, 'page': 57}}}}
    std = {'standards': {}}
    assert pz.additional_units([], lot, 'C1', rules, {}, std)['permitted_in_zone'] is False
    assert pz.additional_units([], lot, 'R9', rules, {}, std) is None
    # A house with 2 m beside it on one side leaves a path; wall to wall, it leaves none.
    monkeypatch.setattr(pz, '_footprints', lambda *a: [box(0, 6, 13, 18)])
    found = pz.additional_units([], lot, 'R4', rules, {}, std)
    assert found['path_fits'] is True and found['max_height_m'] == 4.5 and found['footprint_left_m2'] == 270 - 156
    monkeypatch.setattr(pz, '_footprints', lambda *a: [box(0, 6, 15, 18)])
    found = pz.additional_units([], lot, 'R4', rules, {'provincial_plans': [{'layer': 'Oak Ridges Moraine Boundary', 'distance_m': 0, 'parcel_share_pct': 100, 'attributes': {}}]}, std)
    assert found['path_fits'] is False and len(found['blockers']) == 2
    rules['exceptions'] = {'X12': {'text': '"Dwelling, Detached" shall mean', 'page': 300}, 'X13': {'text': 'a gas station'}}
    assert pz.additional_units([], lot, 'S2-X12', rules, {}, std)['basis'] == 'planning_act'
    assert pz.additional_units([], lot, 'C9-X13', rules, {}, std) is None
    monkeypatch.setattr(pz, '_footprints', lambda *a: [box(15, 6, 20, 18)])  # next door, touching the lot line
    assert pz.additional_units([], lot, 'R4', rules, {}, std)['path_fits'] is None


def test_permitted_uses_name_the_enerzen_units_that_fit():
    from engine import pickering_zoning as pz
    rules = {'uses': {'R3A': {'Apartment Dwelling': {'page': 103}, 'Street Townhouse Dwelling': {}, 'Home Occupation': {}}}}
    found = pz.permitted_uses('R3A-X12', rules)
    assert found['dwellings'] == ['Apartment Dwelling', 'Street Townhouse Dwelling'] and found['other_uses'] == 1
    assert found['enerzen_units'] == ['Townhouse', 'MURB'] and found['page'] == 103
    assert pz.permitted_uses('S2', rules) is None


def test_a_lot_in_a_drawn_block_takes_the_setbacks_of_the_lines_it_is_on(monkeypatch):
    from types import SimpleNamespace
    from shapely import STRtree
    from shapely.geometry import LineString, box
    from engine import pickering_zoning as pz

    def layer(category, name, features):
        return SimpleNamespace(meta={'category': category, 'name': name}, features=features,
                               tree=STRtree([g for _, g in features]), _indexed=list(range(len(features))))
    block = box(0, 0, 40, 30)  # exception X9, two lots side by side, Bayly Street along its south edge
    layers = [layer('zoning', 'Zoning', [({'ZONING_CODE': 'M15', 'EXCEPTION_NUM': '9'}, block)]),
              layer('roads', 'Road Centreline', [({'FULL_NAME': 'Bayly Street W'}, LineString([(-50, -8), (90, -8)]))])]
    figure = [{'figure': 'Figure 1', 'setbacks': [{'from': 'Bayly Street (Regional Road 22)', 'value_m': 4.0, 'stated': '4 m'},
                                                  {'from': 'east lot line (top of bank)', 'value_m': 7.5, 'stated': '7.5 m'}]}]
    lot = lambda: {'exceptions': ['X9'], 'figure_setbacks': figure, 'basis': 'figure', 'complete': False,
                   'setbacks_by_side': {s: {'applies': a, 'value': None} for s, a in
                                        zip('NESW', ('rear_yard', 'interior_side_yard', 'front_yard', 'interior_side_yard'))}}
    east, west = lot(), lot()
    pz._sides_from_figures(layers, box(20, 0, 40, 30), east, {'rotation_deg': 0})
    pz._sides_from_figures(layers, box(0, 0, 20, 30), west, {'rotation_deg': 0})
    assert {s: e['value'] for s, e in east['setbacks_by_side'].items()} == {'N': None, 'E': 7.5, 'S': 4.0, 'W': 0.0}
    assert east['complete'] is False  # the north edge is the block's, and the drawing names no north line
    assert {s: e['value'] for s, e in west['setbacks_by_side'].items()} == {'N': None, 'E': 0.0, 'S': 4.0, 'W': None}
    figure[0]['setbacks'] += [{'from': 'north and west lot lines', 'value_m': 3.0, 'stated': '3 m'}]
    west = lot()
    pz._sides_from_figures(layers, box(0, 0, 20, 30), west, {'rotation_deg': 0})
    assert west['complete'] and west['basis'] == 'figure_mapped' and west['buildable_area_m2'] == (20 - 3) * (30 - 3 - 4)


def test_an_exception_zone_with_an_overlay_suffix_finds_its_provisions():
    from engine import lot_rules
    rules = {'zones': {}, 'exceptions': {'X210': {'by_zone': {'R3-5': {'rear_yard': {'value': 7.5, 'unit': 'm'}}}}}}
    assert lot_rules.resolve('R3-5-ES-X210', rules)['rear_yard']['value'] == 7.5


def test_an_old_exception_falls_back_to_its_former_parent_zone():
    from engine import lot_rules
    rules = {'zones': {}, 'former_of': {'X33': '3036'},
             'former': {'2511': {'zones': {'R4': {'front_yard': {'value': 7.62}, 'rear_yard': {'value': 7.62}, '_section': '10'}}},
                        '3036': {'zones': {'R4': {'front_yard': {'value': 9.0}}}}},
             'exceptions': {'X33': {'text': 'Notwithstanding subsections 10.2.3 of By-law 2511, the minimum front yard is 6.0 metres',
                                    'provisions': {'front_yard': {'value': 6.0}}}}}
    found = lot_rules.resolve('R4-X33', rules)
    assert found['rear_yard']['value'] == 7.62 and 'By-law 2511 (former)' in found['rear_yard']['from']
    assert found['front_yard']['value'] == 6.0  # the exception's own figure still has the last word


def test_a_made_up_zone_takes_the_former_section_its_exception_sends_it_to():
    from engine import lot_rules
    rules = {'zones': {}, 'former': {'2511': {'zones': {'M2S': {'front_yard': {'value': 15.24}, '_section': '18'}}}},
             'exceptions': {'X40': {'text': 'any use of the M2S Zone as per Section 18.1 of By-law 2511; BUILDING '
                                            'RESTRICTIONS: Subject to Section 18.2 of By-law 2511;'}}}
    assert lot_rules.resolve('MC-12-X40', rules)['front_yard']['value'] == 15.24


def test_a_made_up_zone_needs_no_yard_its_requirements_never_name():
    from engine import lot_rules
    text = ('Zone Requirements ("RM-1" Zone) No person shall within the lands designated "RM-1" ... except in '
            'accordance Building Height: maximum 11.0 metres Front Yard Depth: minimum 3.0 metres '
            'Zone Requirements ("S4-9" Zone) Front Yard Depth (minimum): 4.5 metres Rear Yard Depth (minimum): for lot '
            'depths less than or equal to 40.0 metres: 7.5 metres')
    rules = {'zones': {}, 'exceptions': {'X6': {'text': text, 'by_zone': {'RM-1': {'front_yard': {'value': 3.0}}},
                                                'zone_sections': ['RM-1', 'S4-9']}}}
    found = lot_rules.resolve('RM-1-X6', rules)
    assert found['front_yard']['value'] == 3.0 and found['rear_yard']['value'] == 0.0 and found['rear_yard']['none_required']
    assert found['interior_side_yard']['value'] == 0.0
    s49 = lot_rules.resolve('S4-9-X6', rules)
    assert 'rear_yard' not in s49 and s49['interior_side_yard']['value'] == 0.0  # named, though unread: still missing


def test_a_drawing_names_a_street_by_its_old_type():
    from types import SimpleNamespace
    from shapely import STRtree
    from shapely.geometry import LineString, box
    from engine import pickering_zoning as pz
    def layer(category, name, features):
        return SimpleNamespace(meta={'category': category, 'name': name}, features=features,
                               tree=STRtree([g for _, g in features]), _indexed=list(range(len(features))))
    layers = [layer('zoning', 'Zoning', [({'ZONING_CODE': 'M15', 'EXCEPTION_NUM': '1'}, box(0, 0, 40, 30))]),
              layer('roads', 'Road Centreline', [({'FULL_NAME': 'Oklahoma Drive'}, LineString([(-10, -50), (-10, 80)]))])]
    lot = {'exceptions': ['X1'], 'basis': 'figure', 'complete': False,
           'figure_setbacks': [{'figure': 'Figure 1', 'setbacks': [{'from': 'Oklahoma Road', 'value_m': 6.1, 'stated': '20 ft'}]}],
           'setbacks_by_side': {s: {'applies': 'x', 'value': None} for s in 'NESW'}}
    pz._sides_from_figures(layers, box(0, 0, 40, 30), lot, {'rotation_deg': 0})
    assert lot['setbacks_by_side']['W']['value'] == 6.1


def test_a_street_bending_round_a_corner_faces_both_sides_and_a_long_one_only_its_own():
    from types import SimpleNamespace
    from shapely import STRtree
    from shapely.geometry import LineString, box
    from engine import pickering_zoning as pz
    def layer(category, name, features):
        return SimpleNamespace(meta={'category': category, 'name': name}, features=features,
                               tree=STRtree([g for _, g in features]), _indexed=list(range(len(features))))
    roads = [({'FULL_NAME': 'Oklahoma Drive'}, LineString([(-8, 100), (-8, -8), (100, -8)])),  # down the west, along the south
             ({'FULL_NAME': 'Bayly Street'}, LineString([(-300, 38), (300, 38)]))]  # one long piece along the north
    layers = [layer('zoning', 'Zoning', [({'ZONING_CODE': 'M15', 'EXCEPTION_NUM': '1'}, box(0, 0, 40, 30))]),
              layer('roads', 'Road Centreline', roads)]
    lot = {'exceptions': ['X1'], 'basis': 'figure', 'complete': False,
           'figure_setbacks': [{'figure': 'Figure 1', 'setbacks': [{'from': 'Oklahoma Road', 'value_m': 9.1, 'stated': '30 ft'},
                                                                  {'from': 'Bayly Street', 'value_m': 4.0, 'stated': '4 m'}]}],
           'setbacks_by_side': {s: {'applies': 'x', 'value': None} for s in 'NESW'}}
    pz._sides_from_figures(layers, box(0, 0, 40, 30), lot, {'rotation_deg': 0})
    assert {s: e['value'] for s, e in lot['setbacks_by_side'].items()} == {'N': 4.0, 'E': None, 'S': 9.1, 'W': 9.1}


def test_a_rear_yard_set_by_lot_depth_takes_the_deeper_figure_on_a_deep_lot():
    from shapely.geometry import box, LineString
    from engine import lot_rules
    rules = {'zones': {}, 'exceptions': {'X62': {'figures': [{'figure': 'Zone Requirements', 'document': 'd', 'page': 235,
        'yards': {'S4-9': {'rear_yard': 7.5}}, 'deeper': {'rear_yard': [40.0, 10.0]}, 'note': 'by depth', 'setbacks': []}]}}}
    street = [LineString([(-50, -5), (50, -5)])]
    for depth, rear in ((35, 7.5), (45, 10.0)):
        lot = box(0, 0, 15, depth)
        dims = {'width_m': 15, 'depth_m': depth, 'rotation_deg': 0, 'rectangularity': 1, 'street_side': 'S'}
        found = lot_rules.apply_to_lot(lot, 'S4-9-X62', rules, street, dims)
        assert found['setbacks_by_side']['N']['value'] == rear


def test_side_yards_set_by_lot_frontage():
    from shapely.geometry import box, LineString
    from engine import lot_rules
    rules = {'zones': {}, 'exceptions': {'X62': {'figures': [{'figure': 'Zone Requirements', 'document': 'd', 'page': 235, 'setbacks': [],
        'yards': {'S4-9': {'interior_side_yard': 1.2}}, 'other_side': {'interior_side_yard': 0.6},
        'wider': {'interior_side_yard': [[12.0, 1.2, None], [15.0, 1.5, None]]}}]}}}
    street = [LineString([(-50, -5), (50, -5)])]
    for width, sides in ((11, {1.2, 0.6}), (13, {1.2}), (16, {1.5})):
        dims = {'width_m': width, 'depth_m': 30, 'rotation_deg': 0, 'rectangularity': 1, 'street_side': 'S'}
        found = lot_rules.apply_to_lot(box(0, 0, width, 30), 'S4-9-X62', rules, street, dims)
        assert {found['setbacks_by_side'][s]['value'] for s in 'EW'} == sides
