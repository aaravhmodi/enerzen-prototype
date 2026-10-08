from engine.soft import SOFT_COST_FRACTION, soft_cost, soft_timeline


def test_soft_cost_is_a_class_d_allowance_on_hard_cost():
    assert soft_cost(200_000) == round(200_000 * SOFT_COST_FRACTION)


def test_single_house_skips_site_plan_and_gets_house_permit_period():
    timeline = soft_timeline("single_family", 2, 96, 1)
    assert timeline.site_plan_exempt and timeline.site_plan_weeks == 0
    assert timeline.permit_class == "house" and timeline.building_permit_weeks == 2


def test_murb_is_part3_and_needs_site_plan_over_ten_units():
    timeline = soft_timeline("murb", 5, 342, 20)
    assert timeline.permit_class == "part3" and timeline.building_permit_weeks == 4
    assert not timeline.site_plan_exempt and timeline.site_plan_weeks > 8
    assert timeline.total_weeks == timeline.design_engineering_weeks + timeline.site_plan_weeks + timeline.building_permit_weeks
