from engine.finance import CMHC_RENTS, rental_pro_forma


def test_rent_comes_from_cmhc_by_bedrooms_and_energy_scores_mli_select():
    # 20 one-bedroom and 4 three-bedroom homes; EUI 70 against a code-built 130 is 46% better.
    r = rental_pro_forma({1: 20, 3: 4}, 9_000_000, eui=70, code_eui=130)
    rents = CMHC_RENTS['monthly_by_bedrooms']
    assert r['monthly_rent'] == 20 * rents[1] + 4 * rents[3]
    assert r['annual_effective_rent'] == round(12 * r['monthly_rent'] * (1 - CMHC_RENTS['vacancy_rate']))
    mli = r['mli_select']
    assert mli['eligible'] and mli['energy_points'] == 35  # 40% better than code, short of 70%
    assert [o['homes'] for o in mli['affordability_options']] == [3, 4, 6]  # 10%, 15%, 25% of 24, rounded up
    assert mli['max_loan_at_50_points'] == 8_550_000


def test_four_bedrooms_rent_as_three_and_small_projects_are_not_eligible():
    r = rental_pro_forma({3: 1, 4: 2}, 1_000_000, eui=130, code_eui=130)
    assert r['monthly_rent'] == 3 * CMHC_RENTS['monthly_by_bedrooms'][3]
    assert not r['mli_select']['eligible'] and r['mli_select']['energy_points'] == 0
