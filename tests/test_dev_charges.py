import json

from engine import dev_charges
from scripts.dev_charges import read_tables

DURHAM = ['RESIDENTIAL DEVELOPMENT CHARGES (1)', 'Current as of July 1, 2026', 'Single and Medium Apartment Two Apartment',
          'Regional Roads 27,609 21,989 16,074 9,873', 'Total 27,609 21,989 16,074 9,873',
          'Water Supply (2) (3) 22,453 17,881 13,071 8,029', 'Total of All Charges $50,062 $39,870 $29,145 $17,902',
          'COMMERCIAL USE DEVELOPMENT CHARGES']
SEATON = ['Per Residential Dwelling Unit by Type Non-Residential Charges', 'Service Single and Apartments Apartments Other',
          'Parks $19,280 $11,953 $7,508 $14,883 $1.45 $37,862', 'Total DC By-law No. 8190/25 $19,280 $11,953 $7,508 $14,883 $1.45 $1',
          'Total Soft Services2 $1,319 $602 $602 $1,045 $0.153 $0.153', 'Community Uses4 $300 $137 $137 $238 n/a n/a',
          'Total SLG FIA $1,619 $739 $739 $1,283', 'Total Charges - Seaton Lands $20,899 $12,692 $8,247 $16,166 $3.43',
          'Per Residential Dwelling Unit by Type Non-Residential Charges', 'Parks $1 $1 $1 $1']
WATER = ['SEATON RESIDENTIAL AREA SPECIFIC DEVELOPMENT CHARGES (1)(2)', 'EFFECTIVE JULY 1, 2026', 'Single / Medium',
         'Service Category Semi Density', 'Apartments', 'Sanitary Sewerage', 'Seaton Landowners Constructed DCs $ 8,231 $ 6,502 $ 3,787',
         'Water Supply', 'Seaton Landowners Constructed DCs 2,842 2,245 1,308', 'TOTAL $11,073 $8,747 $5,095']


def test_tables_read_by_their_own_totals():
    durham = read_tables(DURHAM)
    assert durham['total'] == {'single_semi': 50062, 'multiples': 39870, 'apartment_2_bed_plus': 29145, 'apartment_1_bed_or_less': 17902}
    assert list(durham['services']) == ['Regional Roads', 'Water Supply'] and durham['effective'] == 'July 1, 2026'
    seaton = read_tables(SEATON)  # "Total Soft Services" adds up to nothing before it, so it is a charge
    assert seaton['total']['single_semi'] == 20899 and 'Total Soft Services' in seaton['services']
    assert seaton['services']['Parks']['multiples'] == 14883 and seaton['services']['Parks']['apartment_2_bed_plus'] == 11953
    water = read_tables(WATER)
    assert list(water['services']) == ['Sanitary Sewerage: Seaton Landowners Constructed DCs', 'Water Supply: Seaton Landowners Constructed DCs']
    assert water['total']['apartment_1_bed_or_less'] == water['total']['apartment_2_bed_plus'] == 5095
    assert read_tables(DURHAM[:-2]) is None  # no total that adds up: nothing is trusted


def test_a_lot_pays_its_area_and_its_services(tmp_path):
    k = lambda v: {'single_semi': v}
    (tmp_path / 'dev_charges.json').write_text(json.dumps({'retrieved_at': 'now', 'schedules': [
        {'authority': 'City of Pickering', 'area': 'citywide', 'url': 'c', 'services': {'Parks': k(100)}, 'education': {'public': 3, 'catholic': 2, 'total': 5}},
        {'authority': 'City of Pickering', 'area': 'seaton', 'url': 's', 'services': {'Parks': k(60)}},
        {'authority': 'Region of Durham', 'area': 'citywide', 'url': 'r', 'services': {'Roads': k(10), 'Water Supply': k(7), 'Sanitary Sewerage': k(3)}},
        {'authority': 'Region of Durham', 'area': 'seaton', 'url': 'rs', 'services': {'Water Supply: Seaton': k(4)}}]}))
    assert dev_charges.for_lot(tmp_path, seaton=False, serviced=True)['total'] == 100 + 20 + 5
    assert dev_charges.for_lot(tmp_path, seaton=False, serviced=False)['total'] == 100 + 10 + 5
    assert dev_charges.for_lot(tmp_path, seaton=True, serviced=True)['total'] == 60 + 10 + 4 + 5
    assert dev_charges.for_lot(tmp_path, seaton=False, serviced=True)['garden_suite'] == {
        'municipal': 0, 'basis': dev_charges.ARU_EXEMPTION, 'school_boards': 5}
