"""Reading zone standards and exceptions out of by-law PDFs laid out the ways Pickering's are."""
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

from scripts import zone_rules
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


def test_each_lot_takes_its_own_row_of_a_seaton_table():
    """By-law 8149/24, Table 14.5 (SLD1): a row per kind of dwelling and access, each kept, and a lot
    takes the row for its own dwelling, its lane and its frontage."""
    from shapely.geometry import LineString, box
    from engine import lot_rules
    head = ['Building\nRequirement', 'Min. Lot\nArea', 'Min. Lot\nFrontage', 'Min.\nFront\nYard', 'Max.\nFront\nYard',
            'Min.\nInterior\nSide\nYard', 'Min. Rear\nYard', 'Min. Front\nYard\nLandscaped\nOpen Space']
    table = [head,
             ['Detached\nDwelling –\naccessed\nfrom a street', '', '', '', '', '', '', ''],
             ['with attached\nprivate\ngarage', '225.0 m2', '9.0 m', '3.0 m(3)', '-', '1.2 m &\n0.6 m',
              '6.0 m /\n5.0 m\nadjacent\nto SNHS\nzone', '25%'],
             ['Detached\nDwelling –\naccessed\nfrom a lane(4)', '', '', '', '', '', '', ''],
             ['with\ndetached\nprivate\ngarage', '210.0 m2', '8.5 m', '3.0 m', '4.5 m', '1.2 m &\n0.6 m', '-', '50%'],
             ['Semi-\ndetached\nDwelling –\naccessed\nfrom a street', '', '', '', '', '', '', ''],
             ['with attached\nprivate\ngarage', '185.0 m2\n/ unit', '7.5 m /\nunit', '3.0 m(3)', '-', '0.9 m(2)',
              '6.0 m /\n5.0 m\nadjacent\nto SNHS\nzone', '22%']]
    title = 'Table 14.5: Lot and Building Requirements for the Seaton Low Density Type 1 (SLD1) Zone'
    found, _ = rules_from_table(table, title, {'page': 180})
    sld1 = found['SLD1']
    assert sld1['interior_side_yard']['other_side'] == 0.6 and sld1['landscaped_area']['value'] == 25.0
    assert sld1['rear_yard']['next_to'] == {'zone': 'SNHS', 'value': 5.0}
    rules = {'zones': found, 'exceptions': {}}
    detached = lot_rules.resolve('SLD1', rules, frontage_m=10.0)
    assert (detached['lot_frontage']['value'], detached['interior_side_yard']['other_side']) == (9.0, 0.6)
    semi = lot_rules.resolve('SLD1', rules, frontage_m=7.6, joined=True)
    assert (semi['lot_frontage']['value'], semi['interior_side_yard']['value'], semi['lot_area']['value']) == (7.5, 0.9, 185.0)
    assert 'other_side' not in semi['interior_side_yard'] and semi['landscaped_area']['value'] == 22.0
    lane = lot_rules.resolve('SLD1', rules, frontage_m=9.0, lane_lot=True)
    assert lane['rear_yard']['none_required'] and lane['rear_yard']['value'] == 0.0 and lane['lot_area']['value'] == 210.0
    assert 'accessed from a lane with detached private garage" row' in lane['front_yard']['from']
    # A street lot whose rear lot line abuts the SNHS zone takes 5.0 m there; its front stays 3.0 m.
    lot, street, heritage = box(0, 0, 10, 30), LineString([(-20, -9), (30, -9)]), box(-5, 30.5, 15, 60)
    dims = {'width_m': 10, 'depth_m': 30, 'rotation_deg': 0.0}
    found_lot = lot_rules.apply_to_lot(lot, 'SLD1', rules, [street], dims, neighbours={'SNHS': [heritage]})
    assert found_lot['setbacks_by_side']['N']['value'] == 5.0 and found_lot['setbacks_by_side']['S']['value'] == 3.0
    # The table runs on to the next page without its title: its rows there are still SLD1's, under the
    # heading open at the foot of the page before.
    carry = {}
    rules_from_table(table[:4], title, {'page': 180}, carry)
    more, _ = rules_from_table([head, table[4]], 'Consolidated Zoning By-law - December 16, 2024 165', {'page': 181}, carry)
    assert more['SLD1']['lot_frontage']['kind'] == 'Detached Dwelling – accessed from a lane with detached private garage'
    assert more['SLD1']['rear_yard']['none_required']
    # Table 14.25: the SSWM zone (printed "SSWMP") requires no yards; Section 14.8.2.2 caps other uses at 12.5 m.
    open_space = [['Zone', 'Min. Front Yard', 'Max. Front Yard', 'Min. Rear Yard', 'Max. Coverage'],
                  ['SOS', '3.0 m', '-', '7.5 m', '5%'], ['SSWMP', '-', '-', '-', '-']]
    parks, _ = rules_from_table(open_space, '2. The maximum height of all other uses shall be 12.5 m.', {'page': 231})
    assert parks['SSWM']['rear_yard']['none_required'] and 'lot_coverage' not in parks['SSWM']
    assert parks['SOS']['building_height']['value'] == 12.5
    # Section 14.9.2.1: an SUT lot takes the most restrictive standards of the zones beside it.
    rules['zones'].update(parks)
    utility = lot_rules.apply_to_lot(lot, 'SUT', rules, [street], dims, neighbours={'SLD1': [heritage], 'SOS': [heritage]})
    assert utility['standards']['rear_yard']['value'] == 7.5 and utility['standards']['front_yard']['value'] == 3.0
    assert 'Section 14.9.2.1' in utility['standards']['rear_yard']['from'] and utility['basis'] == 'yards'
    # The table has no lot coverage column: not regulated by the zone, which is not "not found".
    assert 'lot_coverage' not in found_lot['missing'] and '45%' in found_lot['not_regulated']['lot_coverage']


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
    assert rules['front_yard']['value'] == 4.5 and rules['front_yard']['applies_to'] == ['S1', 'S1-2', 'S3']
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
    for row in table[3:]:  # the yards are one cell merged down all the zones, as unmerged() returns it
        row[4:7] = table[2][4:7]
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


def test_a_newer_exception_table_with_a_column_per_kind_of_lot_runs_over_the_page():
    # Exception 332, as the PDF reader returns its two pages.
    from scripts.zone_rules import rules_by_lot_type
    first = [['', '', '9.0 m single\ndwelling', '12.0 m\nsingle\ndwelling', 'semi-\ndetached\ndwelling', 'Lane\nsingle\nattached\ndwelling'],
             ['', 'Lot Frontage\n(Minimum)', '9.0 m', '12.0 m', '7.5 m', '6.0 m'],
             ['', 'Lot Area\n(Minimum)', '225 square\nmetres', '300\nsquare\nmetres', '180\nsquare\nmetres', '170\nsquare\nmetres'],
             ['', 'Front Yard\nDepth\n(Minimum)', '3.0 m', '3.0 m', '3.0 m', '3.0 m'],
             ['', 'Interior Side\nyard Width\n(Minimum)', '1.2 m on one\nside and 0.6\nm on the', '1.2 m on\none side', '1.2 m,\nexcept', '1.2 m,\nexcept']]
    second = [['', '', 'adjacent lots;', 'adjacent lots;', 'to that wall on either lot;', 'to that wall on either lot'],
              ['', 'Flanking Side\nYard Width\n(Minimum)', '2.4 m', '2.4 m', '2.4 m', '2.4 m'],
              ['', 'Rear Yard\nDepth\n(Minimum)', '7.0 m', '7.0 m', '7.0 m', '12.0 m'],
              ['', 'Lot Coverage of\nAll Accessory\nBuildings', '15 square\nmetres', '15 square\nmetres', '15 square\nmetres', '15 square\nmetres']]
    kinds, types = rules_by_lot_type(first, {'page': 591})
    assert types[0] == '9.0 m single dwelling' and [k['provisions']['lot_frontage']['value'] for k in kinds] == [9.0, 12.0, 7.5, 6.0]
    assert rules_by_lot_type(second, {}) == ([], [])  # no headings of its own
    more, _ = rules_by_lot_type(second, {'page': 592}, types)
    assert [k['provisions']['rear_yard']['value'] for k in more] == [7.0, 7.0, 7.0, 12.0]
    assert 'lot_coverage' not in more[0]['provisions'] and more[0]['provisions']['exterior_side_yard']['value'] == 2.4
    for kind, extra in zip(kinds, more):
        kind['provisions'].update(extra['provisions'])
    from engine.lot_rules import resolve
    rules = {'zones': {}, 'exceptions': {'X332': {'provisions': {}, 'by_lot_type': {'S-SD-SA-3': kinds}}}}
    wide, narrow = resolve('S-SD-SA-3-X332', rules, 12.3), resolve('S-SD-SA-3-X332', rules, 5.8)
    assert wide['lot_area']['value'] == 300 and wide['rear_yard']['from'] == 'Exception X332, "12.0 m single dwelling" column'
    assert narrow['rear_yard']['value'] == 12.0  # 5.8 m measured reaches the 6.0 m lane lot with the half metre's grace
    assert resolve('S-SD-SA-3-X332', rules, 4.0) == {} and resolve('S-SD-SA-3-X332', rules) == {}


def test_a_row_whose_label_the_table_lost_is_read_from_the_page_text():
    # Table 12.3 at the foot of page 130: the reader returns the rear yard's rows without their label.
    table = [['Requirement', 'A', 'Q'], ['Minimum Side Yard (m)\nResidential Uses', '-', '-'], ['', '3.0', '3.0'],
             ['', '-', '-'], ['', '12.0', '12.0']]
    text = 'Requirement A Q\nMinimum Side Yard (m) - -\nResidential Uses 3.0 3.0\nMinimum Rear Yard (m) - -\nResidential Uses 12.0 12.0'
    found, _ = rules_from_table(table, text, {'page': 130})
    assert found['A']['interior_side_yard']['value'] == 3.0 and found['Q']['rear_yard']['value'] == 12.0
    assert found['A']['rear_yard']['label'] == 'Minimum Rear Yard (m) – Residential Uses'


def test_the_common_wall_and_a_side_yard_on_a_street():
    from scripts.zone_rules import rules_by_lot_type, rules_by_zone_row
    kinds, _ = rules_by_lot_type([['', '', 'semi-\ndetached\ndwelling', 'Street\nsingle\nattached\ndwelling'],
                                  ['', 'Lot Frontage\n(Minimum)', '7.5 m', '6.0 m'],
                                  ['', 'Interior Side\nyard Width\n(Minimum)', '1.2 m, except where dwellings on abutting lots share a common wall', '1.2 m']], {})
    side = [k['provisions']['interior_side_yard'] for k in kinds]
    assert 'common wall' in side[0]['common_wall'] and 'common_wall' not in side[1]
    table = [['Zone', 'Symbol', 'Minimum Lot\nFrontage', 'Minimum Yards', '', ''], ['', '', '', 'Front', 'Side', 'Rear'],
             ['Detached', 'S1', '15 metres', '4.5 metres', '1.2 metres unless side yard abuts street then minimum shall be 2.7 metres', '7.5 metres'],
             ['Detached', 'S2', '13.4 metres', '', '', '']]
    table[3][3:] = table[2][3:]  # merged down
    s2 = rules_by_zone_row(table, {})['S2']  # Exception 215
    assert (s2['interior_side_yard']['value'], s2['exterior_side_yard']['value']) == (1.2, 2.7)


def test_merged_cells_take_the_text_of_the_cell_that_spans_them():
    from types import SimpleNamespace as Table
    from scripts.zone_rules import unmerged
    # Exception 295 in small: a heading across two columns, and each yard one cell down three zones.
    table = Table(cells=[(0, 0, 10, 10), (10, 0, 30, 10),                       # 'Symbol' | 'Minimum Yards' across two
                         (0, 10, 10, 20), (10, 10, 20, 40), (20, 10, 30, 40),   # 'S1' | front, three rows deep | rear, three rows deep
                         (0, 20, 10, 30), (0, 30, 10, 40)],                     # 'S2', 'SD'
                  extract=lambda: [['Symbol', 'Minimum Yards', None], ['S1', '4.5 metres', '7.5 metres'],
                                   ['S2', None, None], ['SD', None, None]])
    assert unmerged(table) == [['Symbol', 'Minimum Yards', 'Minimum Yards'], ['S1', '4.5 metres', '7.5 metres'],
                               ['S2', '4.5 metres', '7.5 metres'], ['SD', '4.5 metres', '7.5 metres']]


def test_an_exception_with_several_zones_keeps_each_zones_own_standards():
    # Exception 238: five zones under their own headings, and inside one of them a yard given zone by zone.
    from scripts.zone_rules import exceptions_from_pages
    from engine.lot_rules import resolve
    page = ('Exception Zone 238 (By-law 2015-85)\n'
            'Uses Permitted ("S1", "S1-2", S1-3" and "S3" zone)\nDetached dwelling\n'
            'Zone Requirements ("S1", "S1-2", "S1-3" and "S3" Zones)\n'
            'FRONT YARD DEPTH (minimum):\non lands designated "S1", \'\'S1-2\'\' and \'\'S3\'\':4.5 metres\n'
            'on lands designated "S1-3":   4.0 metres\n'
            'REAR YARD DEPTH (minimum):\non lands designated "S1" and "S3": 7.5 metres\n'
            'on lands designated "S1-2" and "S1-3": see Figure 1 attached\n'
            'Uses Permitted ("S-SD" Zone)\nSemi-detached dwelling\n'
            'Zone Requirements (\'\'S-SD" Zone)\n'
            'FRONT YARD DEPTH (minimum): 6.0 metres\nREAR YARD DEPTH (minimum): 9.0 metres\n')
    rules = {'zones': {}, 'exceptions': exceptions_from_pages([page], {'file': 'f'})}
    yards = lambda code: {k: v['value'] for k, v in resolve(code, rules).items()}
    assert rules['exceptions']['X238']['zone_sections'] == ['S1', 'S1-2', 'S1-3', 'S3', 'S-SD']
    assert yards('S1-X238') == {'front_yard': 4.5, 'rear_yard': 7.5} and yards('S1-3-X238') == {'front_yard': 4.0}
    assert yards('S-SD-X238') == {'front_yard': 6.0, 'rear_yard': 9.0}  # not the first zone's 4.5 and 7.5


def test_a_yard_given_by_kind_of_dwelling_and_the_wall_two_dwellings_share():
    from scripts.zone_rules import exceptions_from_pages, rules_by_zone_row
    page = ('Exception Zone 238 (By-law 2015-85)\nZone Requirements ("S-SD" Zone)\n'
            'INTERIOR SIDE YARD WIDTH (minimum):\nfor detached dwellings: 1.2 metres one side no minimum the\nother side\n'
            'for semi-detached dwellings: 1.2 metres except that no interior side yard shall be required\n'
            'on the side where dwellings on adjacent lots are attached together\n'
            'Zone Requirements ("S1" Zone)\nINTERIOR SIDE YARD WIDTH:\nfor single detached dwellings\n'
            '1) minimum 1.5 metres one side, 0.6 metres other side, or\n')
    zones = exceptions_from_pages([page], {'file': 'f'})['X238']['by_zone']
    assert zones['S-SD']['interior_side_yard']['value'] == 1.2 and 'for detached dwellings' in zones['S-SD']['interior_side_yard']['label']
    assert 'attached together' in zones['S-SD']['interior_side_yard']['common_wall']
    assert zones['S1']['interior_side_yard']['value'] == 1.5 and 'common_wall' not in zones['S1']['interior_side_yard']
    table = [['Zone', 'Symbol', 'Minimum Yards', ''], ['', '', 'Front', 'Side and\nFlankage'],
             ['Single Detached\nDwelling', 'S1', '4.5 metres', '1.2 metres side 2.7 metres flankage'],
             ['Semi-detached\nDwellings', 'SD', '4.5 metres', '1.2 metres side 2.7 metres flankage']]
    rows = rules_by_zone_row(table, {})  # Exception 295
    assert 'common_wall' not in rows['S1']['interior_side_yard'] and 'Semi-detached' in rows['SD']['interior_side_yard']['common_wall']


def test_wordings_from_exceptions_239_139_210_231_and_184():
    read = lambda text: rules_from_text(text, {})
    # The label runs on over two lines before its value (X239).
    side = read('INTERIOR SIDE YARD WIDTH FOR SINGLE DETACHED\nDWELLINGS:\nminimum 1.2 metres one side, 0.6 metres other side, or\n'
                'no minimum one side so long as on the other side:')['interior_side_yard']
    assert (side['value'], side['other_side']) == (1.2, 0.6) and 'SINGLE DETACHED DWELLINGS' in side['label']
    # A kind of dwelling on its own line, then a numbered value; and a scan's "REARYARD" (X139).
    found = read('INTERIOR SIDE YARD WIDTH (minimum):\ndetached dwelling residential use:\n'
                 '1) 0.3 of a metre one side, and 1.2 metres on the other side;\nREARYARD DEPTH (minimum): 7.5 metres;')
    assert (found['interior_side_yard']['value'], found['interior_side_yard']['other_side'], found['rear_yard']['value']) == (0.3, 1.2, 7.5)
    # A yard given zone by zone, each zone's figure a line or more below its name (X210).
    side = read('SIDE YARD WIDTH (minimum):\non the lands designated "S3":\n1) minimum 1.2 metres each side, or\n'
                '2) no minimum one side so long as on the other side:\nI. at least 1.2 metres interior side yard width is provided to\n'
                'the nearest wall of a private garage\non the lands designated "S4":\n1) minimum 1.5 metres each side\n'
                'FLANKAGE SIDE YARD WIDTH (minimum): 2.7 metres')['interior_side_yard']
    assert (side['value'], side['applies_to']) == (1.2, ['S3'])
    assert [(other['value'], other['applies_to']) for other in side['other_zones']] == [(1.5, ['S4'])]
    # The by-law's own slip, "FRONTAGE YARD DEPTH", is the front yard and not the lot's frontage (X231).
    assert read('FRONTAGE YARD DEPTH (minimum):  4.5 metres') == {'front_yard': read('FRONT YARD DEPTH (minimum):  4.5 metres')['front_yard']
                                                                  | {'label': 'FRONTAGE YARD DEPTH (minimum): 4.5 metres'}}
    # A value for each kind of dwelling: the first kind is read (X184).
    front = read('FRONT YARD DEPTH (minimum):\nsemi-detached dwelling: 4.5 metres\nmultiple dwelling - horizontal: 6.0 metres')['front_yard']
    assert front['value'] == 4.5 and 'semi-detached dwelling' in front['label']
    # Still not a standard: a figure, a definition, a sentence that only mentions the yard.
    assert read('REAR YARD DEPTH (minimum):\nsee Figure 1 attached\nFRONT YARD DEPTH (minimum):\nas shown on Schedule 2') == {}


def test_slips_in_the_scans_of_exceptions_217_219_and_330():
    found = rules_from_text('INTERIOR SIDE YARD WIDTH (minima): 1.2 metres, except that\n'
                            'FLANKAGE SIDE YARD WI0TH (minimum): 2. 7 metres\n'
                            'REAR YARD DEPTH (minimum):\nwithin the lands designated \'\'S1\'\': 7.5 metres', {})
    assert {k: v['value'] for k, v in found.items()} == {'interior_side_yard': 1.2, 'exterior_side_yard': 2.7, 'rear_yard': 7.5}
    assert found['rear_yard']['applies_to'] == ['S1']
    assert rules_from_text('INTERIOR SIDE. YARD WIDTH (minimum): 2.4 metres', {})['interior_side_yard']['value'] == 2.4


def test_the_city_centre_table_and_setbacks_that_are_drawn():
    from scripts.zone_rules import DRAWN, exceptions_from_pages
    # Table 8.6: one column for all the City Centre zones; a street-line setback and no yards.
    table = [['Requirement', 'CC Zones'], ['Minimum Building Height (m)', 'As shown on Schedule 5'],
             ['Minimum Building Setback from\nStreet Line (m)', '1.0'], ['Maximum Building Setback\nfrom Street Line (m)', '4.0 (1)(2)'],
             ['Minimum Main Wall Stepback for\nBuildings greater than 37.5 m in\nHeight (m)', 'Minimum main wall stepback - 3.0 m'],
             ['Buildings Requiring Active At\nGrade Frontages', 'Minimum – 40% of the first storey'], ['', 'Minimum ground floor height – 4.5 m']]
    found, _ = rules_from_table(table, '', {'page': 118})
    assert {k: v['value'] for k, v in found['CC*'].items()} == {'street_line_setback': 1.0, 'street_line_setback_max': 4.0}
    assert parse_value('As shown on Schedule 5') is None and parse_value('7.5 m, see Section 4.23')['value'] == 7.5
    # Exceptions whose setbacks are a drawing: kept as what the by-law says and the page it says it on.
    page = ('Exception Zone 103 (By-law 6705-06)\nZone Requirements ("RH-MU-2" Zone)\nBuilding Location and Setbacks:\n'
            'Buildings and structures shall be located entirely within the building\nenvelope shown on Figure 1.\n'
            'Zone Requirements ("MD-H6" Zone)\nFront Yard Depth (minimum): 3.0 metres\nBuilding Height (maximum): as shown on Figure 2\n')
    found = exceptions_from_pages(['', page], {'file': 'f'})['X103']
    assert set(found['by_figure']) == {'*', 'RH-MU-2'} and found['by_figure']['RH-MU-2']['page'] == 2
    assert found['by_figure']['RH-MU-2']['text'].startswith('Building Location and Setbacks: Buildings and structures')
    assert DRAWN.search('Setbacks from streets & property boundaries as per Figure 2 - C1-7 inclusive')


def test_the_other_ways_exceptions_word_a_yard():
    from scripts.zone_rules import exceptions_from_pages, rules_by_zone_column, rules_from_text
    yards = lambda text: {k: v['value'] for k, v in rules_from_text(text, {}).items()}
    # Scan slips and short names.
    assert yards('FRONT YARO DEPTH (minimum):  4.5 metres\nINTERIOR YARD WIDTH (minimum):     7.5 metres') == \
        {'front_yard': 4.5, 'interior_side_yard': 7.5}
    assert yards('FRONT YARD DEPTH· (minimum):  4.5 metres') == {'front_yard': 4.5}
    # A figure for each zone, with or without a colon, and past a zone whose figure is not a width.
    found = rules_from_text('SIDE YARD WIDTH (minimum):\non lands designated “S2-8”: 1.2 metres\non lands designated “S2-9”:\n'
                            '1) north side yard 1.2 metres\n2) south side yard 4.5 metres\non lands designated “S4-2”   \n'
                            '1) minimum 1.2 metres one side, 0.6 metres other side, or\n'
                            'FRONT YARD DEPTH: (minimum)\non lands zoned "SA-12" 4.5 metres', {})
    assert found['interior_side_yard']['applies_to'] == ['S2-8']
    assert [(o['value'], o['other_side'], o['applies_to']) for o in found['interior_side_yard']['other_zones']] == [(1.2, 0.6, ['S4-2'])]
    assert (found['front_yard']['value'], found['front_yard']['applies_to']) == (4.5, ['SA-12'])
    # The standard restated as a sentence; and some lots set apart from all the others.
    assert yards('Rear Yard Depth (minimum):\nthe minimum rear yard depth for all lots shall be 7.5 metres;') == {'rear_yard': 7.5}
    found = rules_from_text('FRONT YARD DEPTH (minimum):\nfor lots fronting on Fairport Road: 7.5 metres\nfor all other lots: 4.5 metres\n'
                            'Rear Yard Depth (minimum):\nfor lot depths less than or equal to 40.0 metres: 7.5 metres', {})
    assert set(found) == {'front_yard'} and found['front_yard']['value'] == 4.5 and 'Fairport Road' in found['front_yard']['varies']
    # One heading for both side yards; a list of encroachments is still not a standard.
    assert yards('SIDE YARD WIDTHS (minimal):\ninterior side yard: 1.5 metres, except that no interior side yard shall\n'
                 'flankage side yard:  3 metres\nbay windows may encroach as follows:\n1) front yard: 0.6 metres') == \
        {'interior_side_yard': 1.5, 'exterior_side_yard': 3.0}
    # A label at the foot of a page, its figure at the top of the next.
    pages = ['Exception Zone 43\nZone Requirements ("R4-13" Zone)\nFRONT YARD DEPTH (minimum):\n164\n',
             'Section 15 | Exceptions\nCity of Pickering\n4.5 metres, or\n7.5 metres for the area diagonally hatched on Figure 1\n'
             'REAR YARD DEPTH (minimum): 7.5 metres\n']
    found = exceptions_from_pages(pages, {})['X43']['by_zone']['R4-13']
    assert {k: (v['value'], v['page']) for k, v in found.items()} == {'front_yard': (4.5, 1), 'rear_yard': (7.5, 2)}
    # An exception's table with a column per zone.
    table = [[None, None, '“R3” Zone', '“S3-7” Zone'], ['(c)', 'Front Yard Depth (minimum)', '7.5 metres', '4.5 metres'],
             ['(e)', 'Side Yard Width (minimum)', '1.5 metres', 'minimum side yard depth of 1.2 metres on one side and 0.6 metres on the other side'],
             ['(f)', 'Rear Yard Depth (minimum)', 'i) 7.5 metres ii) 6.0 metres for the lands in the hatched area', 'n/a'],
             ['(j)', 'Lot Coverage of All Accessory Buildings', '15.0 square metres', '15.0 square metres']]
    found = rules_by_zone_column(table, {'page': 489})
    assert {k: v['value'] for k, v in found['R3'].items()} == {'front_yard': 7.5, 'interior_side_yard': 1.5, 'rear_yard': 7.5}
    assert found['S3-7']['interior_side_yard']['other_side'] == 0.6 and 'rear_yard' not in found['S3-7']
    assert rules_by_zone_column([['', 'R1A', 'R1B'], ['Minimum Front Yard (m)', '6', '7']], {}) == {}


def test_a_yard_for_each_kind_of_dwelling_and_for_each_size_of_lot():
    from scripts.zone_rules import rules_from_text
    found = rules_from_text('FRONT YARD DEPTH (minimum per dwelling unit):\ndetached dwelling 2.6 metres\nmultiple dwelling – horizontal 4.5 metres\n'
                            'despite subsection B above, on the lands shaded on Figure 1, a\nmultiple dwelling – horizontal may provide a minimum front yard\n'
                            'depth of 2.6 metres;\nINTERIOR SIDE YARD WIDTH (minimum):\nfor detached dwellings  minimum 1.2 metres one side, no\n'
                            'minimum the other provided that the aggregate of actual side yard\nfor semi detached dwellings minimum 0.6 metres except that,\n'
                            'which that dwelling is located;\n1) minimum 1.2 metre interior side yard shall be provided\n'
                            'SIDE YARD WIDTH (Minimum)\nFlankage Side Yard - 12 metres, except that where', {})
    kinds = lambda rule: [(rule['kind'], rule['value'], rule.get('other_side'))] + [(k['kind'], k['value'], k.get('other_side')) for k in rule.get('other_kinds', [])]
    assert kinds(found['front_yard']) == [('detached dwelling', 2.6, None), ('multiple dwelling – horizontal', 4.5, None)]
    assert kinds(found['interior_side_yard']) == [('detached dwellings', 1.2, 0.0), ('semi detached dwellings', 0.6, None)]
    assert found['exterior_side_yard']['value'] == 12.0
    slip = rules_from_text('INTERIOR SIDE YARD WIHDTH:\nno minimum one side, minimum 1.8 metres other side', {})['interior_side_yard']
    assert (slip['value'], slip['other_side']) == (1.8, 0.0)
    # The ORMA zone: one figure for lots over four hectares, one for smaller lots.
    table = [['Requirement', 'ORMA', 'ORMC'], ['Minimum Lot Area (ha)', '> 4 ha: 4.0\n< 4 ha: 0.8', '-'],
             ['Minimum Front Yard (m)', '> 4 ha: 15.0\n< 4 ha: 12.0', '-']]
    orma = rules_from_table(table, '', {})[0]['ORMA']
    assert (orma['front_yard']['value'], orma['front_yard']['small_lot']) == (15.0, {'below_ha': 4.0, 'value': 12.0})
    assert orma['lot_area']['unit'] == 'ha'


def test_a_scan_that_spaces_a_decimal_point_and_a_site_whose_standards_are_on_its_figure():
    from scripts.zone_rules import DRAWN, rules_from_text
    found = rules_from_text('INTERIOR SIDE YARD WIDTH:\nfor single detached dwellings:\n1.2 metres one side, 0.6 metres other side\n'
                            'for all other semi-detached dwellings:\n1 .2 metres one side, 0.6 metres other side, or', {})
    assert found['interior_side_yard']['other_kinds'][0]['value'] == 1.2
    assert DRAWN.search('The performance standards and provisions as set out on Figure 1 hereto shall apply to the area')


def test_additional_unit_rows_keep_blank_cells_and_the_section_figures():
    pages = ['Permitted Use R3A R3B R3C \nResidential Uses \nAdditional Dwelling \nUnit(1, 2) ● ●  \n',
             'Permitted Use I1 UR UT \nAdditional Dwelling Unit (2)  ●(1)  \n',
             '4.3 Additional Dwelling Units \n1. Where permitted by this By-law, a maximum of one (1) additional '
             'dwelling unit is permitted within an accessory building. A maximum floor area of 150 sq. m. \n'
             'Requirement Lots with an area of 2,000 \nsq.m. or less \nMaximum Height (m) 4.5 6.5 \n'
             'minimum 1.2 m wide path of travel \n4.4 Air Conditioners \nmaximum floor area of 99 sq. m']
    found = zone_rules.additional_units_from_pages(pages, {'document': 'By-law 8149/24'})
    assert {z: v['permitted'] for z, v in found['zones'].items()} == {
        'R3A': True, 'R3B': True, 'R3C': False, 'I1': False, 'UR': True, 'UT': False}
    assert found['zones']['UR']['notes'] == ['1'] and found['zones']['R3A']['page'] == 1
    section = found['sections']['4.3']
    assert (section['max_floor_area_m2'], section['large_lot_m2'], section['max_height_m'],
            section['max_height_large_lot_m'], section['path_width_m'], section['page']) == (150, 2000, 4.5, 6.5, 1.2, 3)


def test_every_use_a_table_marks_with_wrapped_names_and_blank_cells():
    page = ('Table 6.8 \nPermitted Use R3A R3B R3C \nResidential Uses \nAdditional Dwelling \nUnit(1, 2) ● ●  \n'
            'Apartment Dwelling ●(3) ● ● \nBack-to-Back \nTownhouse \nDwelling \n ●  \nStreet Townhouse \n'
            'Dwelling  ●(3) ●(3)  \nNotes: \n1. Subject to Section 4. \nDetached Dwelling ● ● ●')
    uses = zone_rules.uses_from_pages([page], {'document': 'By-law 8149/24'})
    assert sorted(uses['R3A']) == ['Additional Dwelling Unit', 'Apartment Dwelling', 'Street Townhouse Dwelling']
    assert sorted(uses['R3B']) == ['Additional Dwelling Unit', 'Apartment Dwelling', 'Back-to-Back Townhouse Dwelling',
                                   'Street Townhouse Dwelling']
    assert sorted(uses['R3C']) == ['Apartment Dwelling'] and uses['R3A']['Apartment Dwelling']['notes'] == ['3']


def test_a_bare_dash_under_a_minimum_needs_none_and_a_noted_dash_waits_for_its_note():
    rows = [['Requirement', 'I1', 'UR', 'UT'], ['Minimum Front Yard (m)', '4.0', '-(1)', '-'],
            ['Maximum Building Height (m)', '12.0', '-(1)', '-']]
    found, _ = rules_from_table(rows, '', {'document': 'By-law 8149/24', 'page': 138})
    assert found['UT']['front_yard']['value'] == 0.0 and found['UT']['front_yard']['none_required']
    assert 'building_height' not in found['UT'] and 'front_yard' not in found.get('UR', {})


def test_a_former_bylaws_zone_sections_in_feet_and_the_volumes_its_exceptions_came_from():
    pages = ['SECTION 5 - GENERAL PROVISIONS FOR ALL ZONES Side Yard - Minimum 99 feet',
             'SECTION 10 - ONE-FAMILY DETACHED DWELLING FOURTH DENSITY ZONE R-4 The following 10.2.1 Lot Frontage: Minimum - '
             '50 feet 10.2.2 Lot Area: Minimum - 5,000 square feet 10.2.3 Yard Requirements: Front Yard - Minimum 25 feet '
             'Rear Yard 25 feet minimum Side Yard Minimum one side six (6) feet, other side ten (10) feet 10.2.6 Lot '
             'Coverage: Maximum - l0 per cent',
             'SECTION 14 - GENERAL COMMERCIAL ZONE C2 Front Yard - Minimum 60 feet']
    zones = zone_rules.former_zones(pages, {'document': 'By-law 2511 (former parent by-law)'})
    r4 = zones['R4']
    assert (r4['lot_frontage']['value'], r4['lot_area']['value'], r4['front_yard']['value'], r4['rear_yard']['value']) == (15.24, 464.52, 7.62, 7.62)
    assert (r4['interior_side_yard']['value'], r4['interior_side_yard']['other_side'], r4['lot_coverage']['value']) == (1.83, 3.05, 10.0)
    assert r4['front_yard']['page'] == 2 and zones['C2']['front_yard']['value'] == 18.29 and 'S' not in zones
    volumes = zone_rules.former_volumes([{'url': 'x/2511_-Exception-Zones_V3-X1-to-X3-X413-to-X414---CLEAN.pdf'}])
    assert volumes == {'X1': '2511', 'X2': '2511', 'X3': '2511', 'X413': '2511', 'X414': '2511'}
