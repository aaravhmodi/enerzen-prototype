"""Reading zone standards and exceptions out of by-law PDFs laid out the ways Pickering's are."""
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

from scripts.zone_rules import extract, parse_value, provision_key, rules_from_table, rules_from_text

STYLE = getSampleStyleSheet()


def ruled(rows):
    table = Table(rows)
    table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    return table


def bylaw_pdf(path):
    story = [
        Paragraph('Table 7: Lot and Building Requirements - Low Density Residential Zones', STYLE['Heading2']),
        ruled([['Requirement', 'R3', 'R4', 'R5'],
               ['Minimum Lot Frontage', '18.0 m', '15.0 m', '12.0 m'],
               ['Minimum Lot Area', '550 m2', '460 m2', '370 m2'],
               ['Minimum Front Yard', '7.5 m', '6.0 m', '4.5 m'],
               ['Minimum Interior Side Yard', '1.5 m', '1.2 m', '1.2 m'],
               ['Minimum Exterior Side Yard', '4.5 m', '4.5 m', '2.7 m'],
               ['Minimum Rear Yard', '7.5 m', '7.5 m', '7.0 m'],
               ['Maximum Lot Coverage', '33%', '38%', '40%'],
               ['Maximum Building Height', '9.0 m', '9.0 m', '12.0 m']]),
        PageBreak(),
        Paragraph('Table 9: Lot and Building Requirements', STYLE['Heading2']),
        ruled([['Zone', 'Minimum Front Yard', 'Minimum Rear Yard', 'Maximum Height'],
               ['RM1', '4.5 m', '6.0 m', '12.5 m'],
               ['RM2', '3.0 m', '6.0 m', 'N/A']]),
        PageBreak(),
        Paragraph('Table 12: MU1 Zone Requirements', STYLE['Heading2']),
        ruled([['Minimum Front Yard', '0.0 m'], ['Minimum Rear Yard', '7.5 m'], ['Maximum Building Height', '25 m'],
               ['Bicycle parking ratio', '0.5 per unit']]),
        PageBreak(),
        Paragraph('Section 17 Exceptions', STYLE['Heading2']),
        Paragraph('X 12', STYLE['Normal']),
        Paragraph('Notwithstanding Table 7, for lands zoned R4-X12:', STYLE['Normal']),
        Paragraph('Minimum front yard: 4.5 metres.', STYLE['Normal']),
        Paragraph('Maximum lot coverage: 45%.', STYLE['Normal']),
        Spacer(1, 12),
        Paragraph('X 446', STYLE['Normal']),
        Paragraph('Minimum rear yard: 370 metres.', STYLE['Normal']),
    ]
    SimpleDocTemplate(str(path), pagesize=letter).build(story)


def pages_of(path):
    from pypdf import PdfReader
    return [p.extract_text() or '' for p in PdfReader(path).pages]


def test_tables_in_every_orientation_and_exceptions(tmp_path):
    pdf = tmp_path / 'docs' / 'bylaw-8149-24.pdf'
    pdf.parent.mkdir()
    bylaw_pdf(pdf)
    (tmp_path / 'docs' / 'bylaw.pages.json').write_text(json.dumps(pages_of(pdf)))
    rules = extract([{'kind': 'pdf', 'title': 'Zoning By-law 8149/24', 'url': 'u', 'file': 'docs/bylaw-8149-24.pdf',
                      'text_file': 'docs/bylaw.pages.json'}], tmp_path)
    r4 = rules['zones']['R4']
    assert {k: (v['value'], v['unit'], v['bound']) for k, v in r4.items()} == {
        'lot_frontage': (15.0, 'm', 'minimum'), 'lot_area': (460.0, 'm2', 'minimum'),
        'front_yard': (6.0, 'm', 'minimum'), 'interior_side_yard': (1.2, 'm', 'minimum'),
        'exterior_side_yard': (4.5, 'm', 'minimum'), 'rear_yard': (7.5, 'm', 'minimum'),
        'lot_coverage': (38.0, '%', 'maximum'), 'building_height': (9.0, 'm', 'maximum')}
    assert r4['front_yard']['page'] == 1 and r4['front_yard']['document'] == 'Zoning By-law 8149/24'
    assert rules['zones']['RM2']['front_yard']['value'] == 3.0 and 'building_height' not in rules['zones']['RM2']
    assert rules['zones']['MU1']['building_height']['value'] == 25 and rules['zones']['MU1']['front_yard']['page'] == 3
    assert any(u['label'] == 'Bicycle parking ratio' for u in rules['unparsed'])  # numeric, unplaced, reported
    x12 = rules['exceptions']['X12']
    assert x12['provisions']['front_yard']['value'] == 4.5 and x12['provisions']['lot_coverage']['value'] == 45
    assert x12['page'] == 4
    assert rules['exceptions']['X446']['provisions']['rear_yard']['value'] == 370


def test_older_exception_headings_and_prose():
    from scripts.zone_rules import exceptions_from_pages
    found = exceptions_from_pages(['Exception Zone 1 (By-law 300-75)\nMinimum side yard 1.8 metres\n'
                                   'Exception Zone 2\nMaximum height of 2 storeys'], {'file': 'f'})
    assert found['X1']['provisions']['interior_side_yard']['value'] == 1.8
    assert found['X2']['provisions']['building_height'] == {**found['X2']['provisions']['building_height'],
                                                            'value': 2.0, 'unit': 'storeys', 'bound': 'maximum'}


def test_labels_and_values():
    assert provision_key('Min. Exterior Side Yard (corner lot)') == ('exterior_side_yard', 'minimum')
    assert provision_key('Minimum Interior Side Yard') == ('interior_side_yard', 'minimum')
    assert provision_key('Parking spaces') is None
    assert parse_value('N/A') is None and parse_value('–') is None
    assert parse_value('7,5 m')['value'] == 7.5
    assert rules_from_text('The minimum rear yard shall be 7.5 metres', {})['rear_yard']['value'] == 7.5


def test_real_bylaw_symbols_and_thousands():
    # By-law 8149/24: zones named R1A to R1I across the top, and "3,000" m2 lot areas.
    table = [['Requirement', 'R1A', 'R1G'],
             ['Minimum Lot Area (m2)', '3,000', '400.0'],
             ['Minimum Front Yard (m)', '9.0', '4.5(1)']]
    found, _ = rules_from_table(table, '', {'page': 99})
    assert found['R1A']['lot_area']['value'] == 3000 and found['R1G']['front_yard']['value'] == 4.5
    assert parse_value('7,5 m')['value'] == 7.5


def test_footnote_marks_and_split_rows():
    assert parse_value('-(1)') is None and parse_value('9.0(1)')['value'] == 9.0
    table = [['Requirement', 'A', 'Q'], ['Minimum Lot Area (ha)\nResidential uses\nOther uses', '', '-'],
             ['', '0.8', '-'], ['', '4.0', '4.0']]
    found, _ = rules_from_table(table, '', {'page': 130})
    assert found['A']['lot_area']['value'] == 0.8 and found['Q']['lot_area']['value'] == 4.0


def test_one_zone_table_by_building_type_keeps_the_first_type():
    table = [['Building\nRequirement', 'Min. Lot\nArea', 'Min.\nFront\nYard', 'Min.\nFlankag\ne Yard', 'Min. Rear\nYard'],
             ['Detached\nDwelling', '', '', '', ''],
             ['with attached\nprivate garage', '225.0 m2', '3.0 m(3)', '2.4 m', '6.0 m'],
             ['with detached\nprivate garage', '275.0 m2', '4.5 m', '2.4 m', '7.0 m']]
    title = 'Table 14.5: Lot and Building Requirements for the Seaton Low Density Type 1 (SLD1) Zone'
    found, _ = rules_from_table(table, title, {'page': 180})
    assert found['SLD1']['front_yard']['value'] == 3.0 and found['SLD1']['exterior_side_yard']['value'] == 2.4
    assert 'Detached Dwelling with attached private garage' in found['SLD1']['front_yard']['label']


def test_prose_takes_only_a_number_that_follows_the_provision_name():
    text = ('"Front Yard Depth" shall mean the shortest horizontal di1nension of a front yard\n'
            'no accessory building shall be erected in the rear yard and shall not be less than 1.0 metres from\n'
            'FRONT YARD DEPTH (minimum): 4.5 metres\nREAR YARD DEPTH (minimum): 7.5 metres\n'
            'FLANKAGE SIDE YARD WIDTH (minimum): 2. 7 metres\nThe minimum interior side yard shall be 1.2 metres')
    rules = rules_from_text(text, {})
    assert {k: v['value'] for k, v in rules.items()} == {
        'front_yard': 4.5, 'rear_yard': 7.5, 'exterior_side_yard': 2.7, 'interior_side_yard': 1.2}


def test_a_value_on_the_line_after_its_label_and_the_zones_it_names():
    text = ('FRONT YARD DEPTH (minimum):\non lands designated "S1", \'\'S1-2\'\' and "S3":4.5 metres\n'
            'INTERIOR SIDE YARD WIDTH:\nminimum 1.2 metres each side, or\n'
            'REAR YARD DEPTH (minimum):\nas shown on the site plan attached as Figure 1')
    rules = rules_from_text(text, {})
    assert rules['front_yard']['value'] == 4.5 and rules['front_yard']['applies_to'] == ['S1', 'S1-2', 'AND', 'S3']
    assert rules['interior_side_yard']['value'] == 1.2 and 'applies_to' not in rules['interior_side_yard']
    assert 'rear_yard' not in rules
    from engine.lot_rules import resolve
    section = {'exceptions': {'X238': {'provisions': rules}}}
    assert 'front_yard' in resolve('S1-X238', section) and 'front_yard' not in resolve('S4-X238', section)


def test_encroachments_wrapped_clauses_and_page_numbers_are_not_standards():
    # Exception X332: the only bare "front yard: 0.6 metres" is how far a bay window may reach.
    text = ('bay, bow or box windows may encroach a maximum into required\nyards as follows:\n'
            '1) front yard: 0.6 metres;\n2) flankage yard: 0.6 metres;\n'
            'dwellings attached above grade may have a\nminimum side yard width of 0.0 metres\n'
            'FRONT YARD DEPTH (minimum): 164\nREAR YARD DEPTH (minimum): 7.5 metres')
    assert {k: v['value'] for k, v in rules_from_text(text, {}).items()} == {'rear_yard': 7.5}


def test_a_lower_case_list_item_under_another_heading_is_not_the_zone_standard():
    # Exception X332: "Detached Garage Requirements:" then bulleted yards for the garage.
    text = ('Detached Garage Requirements:\n\uf0b7 minimum side yard width of 0.0 metres;\n'
            '\uf0b7 minimum rear yard depth of 0.6 metres;')
    assert rules_from_text(text, {}) == {}


def test_an_exception_table_with_a_row_per_zone_two_heading_rows_and_merged_cells():
    # Exception 295, "Figure 1", as the PDF reader returns it.
    from scripts.zone_rules import rules_by_zone_row
    table = [
        ['Zone', 'Symbol', 'Maximum Density', '', 'Minimum Yards', '', '', 'Minimum Ground Floor\nArea/'],
        ['', '', 'Minimum\nFrontage', 'Minimum Lot\nArea/Dwelling', 'Front', 'Side and\nFlankage', 'Rear', 'Bung.'],
        ['Single\nDetached\nDwelling', 'S1', '1 dwelling\nper\nregistered\nlot\n15 metres\n16.5 metres\ncorner lot',
         '510 square\nmetres', '4.5\nmetres',
         '1.2\nmetres\nside\n2.7\nmetres\nflankage', '7.5\nmetres', '110'],
        ['Single\nDetached\nDwelling', 'S2', '13.4 metres\n15 metres\ncorner lot', '450 square\nmetres', '', '', '', ''],
        ['Semi-detached\nDwellings', 'SD', '18 metres', '275 square\nmetres', '', '', '', ''],
    ]
    found = rules_by_zone_row(table, {'page': 374})
    values = lambda zone: {k: v['value'] for k, v in found[zone].items()}
    assert values('S1') == {'lot_frontage': 15.0, 'lot_area': 510.0, 'front_yard': 4.5, 'interior_side_yard': 1.2,
                            'exterior_side_yard': 2.7, 'rear_yard': 7.5}
    assert values('S2') == {**values('S1'), 'lot_frontage': 13.4, 'lot_area': 450.0}  # yards merged down from S1
    assert found['SD']['front_yard']['label'] == 'Minimum Yards: Front yard'
    from engine.lot_rules import resolve
    rules = {'zones': {}, 'exceptions': {'X295': {'provisions': {}, 'by_zone': found}}}
    assert resolve('S2-X295', rules)['rear_yard']['value'] == 7.5 and 'rear_yard' not in resolve('S4-X295', rules)
    assert rules_by_zone_row([['Requirement', 'R1A', 'R1B'], ['Minimum Front Yard (m)', '9.0', '9.0']], {}) == {}
    # Exception 289 gives the two widths without naming them; the heading's order says which is which.
    table[2][5] = '1.2\nmetres\n2.7\nmetres'
    again = rules_by_zone_row(table, {})['S1']
    assert (again['interior_side_yard']['value'], again['exterior_side_yard']['value']) == (1.2, 2.7)
