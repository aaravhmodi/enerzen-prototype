"""Refresh the pilot snapshot from official GIS and EWRB sources.

Prints JSON for review before replacing data/pickering.json. Requires openpyxl
only for this offline import, not on the API server.
"""
import io
import json
import math
from datetime import datetime, timezone
from statistics import median
from urllib.request import Request, urlopen

import openpyxl

GIS = 'https://maps.pickering.ca/arcgisinter/rest/services/public/OpenData/MapServer'
ENERGY = 'https://data.ontario.ca/en/dataset/0eab2faf-6186-4a5b-8de1-b15872943c24/resource/aeb34aef-5029-4b65-8093-c86ad682b037/download/odc_final_dataset_2024.xlsx'


def read_json(url):
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0 EnerZen-data-import'}), timeout=30) as response:
        value = json.load(response)
    if 'error' in value:
        raise ValueError(value['error'])
    return value


def build_snapshot():
    with urlopen(ENERGY, timeout=30) as response:
        workbook = openpyxl.load_workbook(io.BytesIO(response.read()), read_only=True, data_only=True)
    rows = workbook.active.iter_rows(values_only=True)
    headers = next(rows)
    records = [dict(zip(headers, row)) for row in rows if str(row[1]).strip().casefold() == 'pickering']
    housing = [row for row in records if row['PrimPropTypCalc'] == 'Multifamily Housing']
    usable = [row for row in housing if isinstance(row['WN_Site_EUI1'], (int, float)) and math.isfinite(row['WN_Site_EUI1']) and row['WN_Site_EUI1'] > 0]
    values = sorted(row['WN_Site_EUI1'] / 0.0036 for row in usable)
    if not values:
        raise ValueError('No usable multifamily records; do not overwrite snapshot')
    def percentile(p):
        position = (len(values) - 1) * p
        low = int(position)
        high = min(low + 1, len(values) - 1)
        return round(values[low] + (values[high] - values[low]) * (position - low), 1)
    layers = []
    for layer, label in [(6, 'Building footprints'), (3, 'Parks inventory'), (7, 'Neighbourhoods'), (12, 'Residential development records')]:
        count = read_json(f'{GIS}/{layer}/query?where=1%3D1&returnCountOnly=true&f=json')['count']
        layers.append({'label': label, 'count': count, 'source_url': f'{GIS}/{layer}'})
    neighbourhoods = read_json(f'{GIS}/7/query?where=1%3D1&outFields=Nhood&returnGeometry=false&f=json')
    return {
        'municipality': 'Pickering', 'scope': 'citywide', 'retrieved_at': datetime.now(timezone.utc).date().isoformat(),
        'parcel_selected': False, 'layers': layers,
        'neighbourhoods': sorted(f['attributes']['Nhood'] for f in neighbourhoods['features']),
        'geometry_note': 'City-wide inventory only. The clipParcelBoundary layer returns a single feature and is not treated as an individual-lot dataset. No pilot parcel is selected.',
        'sources': [
            {'label': 'City GIS and open data', 'url': GIS},
            {'label': 'Zoning maps and by-laws', 'url': 'https://www.pickering.ca/business-building-development/planning-and-development/zoning/'},
            {'label': 'Sustainable development standards', 'url': 'https://www.pickering.ca/business-building-development/planning-and-development/sustainable-development/'},
            {'label': 'Municipal energy reports', 'url': 'https://www.pickering.ca/property-roads-safety/sustainability-sustainable/energy-and-greenhouse-gas-emissions/'},
            {'label': 'Ontario 2024 building energy data', 'url': ENERGY},
        ],
        'energy_benchmark': {
            'source_year': 2024, 'municipality': 'Pickering', 'reported_rows': len(housing),
            'city_reported_rows': len(records), 'usable_eui_rows': len(values),
            'median_kwh_m2_yr': round(median(values), 1), 'p25_kwh_m2_yr': percentile(.25), 'p75_kwh_m2_yr': percentile(.75),
            'source_url': ENERGY, 'source_field': 'WN_Site_EUI1', 'conversion': 'GJ/m2 / 0.0036 = kWh/m2',
            'limitation': 'Self-reported large multifamily buildings only; small sample, not a low-rise calibration or a target for new homes. Data Quality Checker Run does not mean validated.',
            'records': [{'id': r['EWRB_ID'], 'eui_gj_m2': r['WN_Site_EUI1'], 'quality_checker_run': r['Data_Qual_Check']} for r in usable],
        },
    }


if __name__ == '__main__':
    print(json.dumps(build_snapshot(), indent=2))
