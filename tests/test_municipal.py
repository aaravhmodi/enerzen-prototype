from statistics import median
from api.main import location_detail, zoning_lookup
from engine.municipal import pickering_context


def test_pickering_data_is_local_and_not_parcel_approval():
    detail = location_detail('Pickering (Dunbarton)')
    assert detail['municipal_context']['scope'] == 'citywide'
    assert detail['municipal_context']['parcel_selected'] is False
    assert detail['regulatory_intelligence']['status'] == 'not_checked'
    assert detail['multifamily_energy_benchmark']['municipality'] == 'Pickering'
    assert zoning_lookup('Pickering (Dunbarton)', 43.84, -79.09)['status'] == 'not_available'


def test_energy_units_and_sample_are_traceable():
    benchmark = pickering_context()['energy_benchmark']
    values = [record['eui_gj_m2'] / .0036 for record in benchmark['records']]
    assert benchmark['usable_eui_rows'] == len(values) == 9
    assert benchmark['median_kwh_m2_yr'] == round(median(values), 1)
    assert benchmark['p25_kwh_m2_yr'] <= benchmark['median_kwh_m2_yr'] <= benchmark['p75_kwh_m2_yr']


def test_other_city_does_not_inherit_pickering():
    assert location_detail('Toronto')['municipal_context'] is None
