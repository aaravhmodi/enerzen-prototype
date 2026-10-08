from engine.archetypes import ARCHETYPES
from engine.dev_optimizer import DevSpec, evaluate_dev_mixes, screen_dev_mixes


def _dev(**overrides):
    base = dict(lot_width_m=30, lot_depth_m=50, street_side="N", total_budget_cad=1_500_000,
                location="Pickering (Dunbarton)", allowed_types=["garden_suite", "three_bhk"],
                weights={"yield": 100, "cost": 0, "energy": 0, "carbon": 0})
    base.update(overrides)
    return DevSpec(**base)


def test_screening_returns_fitting_scenarios_without_optimizing():
    scenarios = screen_dev_mixes(_dev())
    assert scenarios
    assert all(s.screening_cost <= 1_500_000 for s in scenarios)
    assert scenarios[0].dwellings == max(s.dwellings for s in scenarios)


def test_evaluation_ranks_approved_mixes_and_adds_development_calculations():
    dev = _dev()
    scenarios = screen_dev_mixes(dev, top_n=4)
    results, rejected = evaluate_dev_mixes(dev, [s.units for s in scenarios])
    assert len(results) + len(rejected) == len(scenarios)
    for r in results:
        assert r.total_cost <= dev.total_budget_cad
        assert r.total_project_cost > r.total_cost
        assert r.soft_timeline_weeks > 0 and r.construction_weeks > 0


def test_a_murb_counts_all_of_its_dwellings():
    dev = _dev(lot_width_m=45, lot_depth_m=60, total_budget_cad=30_000_000, allowed_types=["murb"])
    results, _ = evaluate_dev_mixes(dev, [{"murb": 1}])
    murb = ARCHETYPES["murb"]
    assert results[0].total_units == murb.units_per_building
    assert results[0].total_floor_area_m2 == murb.floor_area_m2


def test_over_budget_scenario_is_rejected_with_a_reason():
    dev = _dev(total_budget_cad=50_000)
    _, rejected = evaluate_dev_mixes(dev, [{"garden_suite": 2}])
    assert rejected and "budget" in rejected[0]["reason"]
