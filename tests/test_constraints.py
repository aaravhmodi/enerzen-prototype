import pytest
from fastapi import HTTPException

from api.main import (DevOptimizeRequest, DevSpecIn, OptimizeRequest, ProjectSpecIn, run_dev_scenarios,
                      run_optimize)
from engine.dev_optimizer import DevSpec, evaluate_dev_mixes, excluded_types, screen_dev_mixes
from engine.optimizer import ProjectSpec, allowed_mechanical, load_catalog, optimize, optimize_with_gate


def _spec(**overrides):
    base = dict(typology="single_family", climate_zone="6", floor_area_m2=150, storeys=2, orientation="S",
                window_to_wall_ratio=0.2, budget_per_unit=1_000_000, target_label="code",
                location="Pickering (Dunbarton)", footprint_length_m=12, footprint_width_m=8)
    base.update(overrides)
    return ProjectSpec(**base)


def test_excluded_systems_never_reach_the_results():
    excluded = ["M1"]
    results = optimize(_spec(excluded_mechanical_ids=excluded))
    assert results
    assert all(r.mechanical_id not in excluded for r in results)


def test_exclusions_combine_with_all_electric():
    catalog = load_catalog()
    allowed = allowed_mechanical(_spec(allow_gas=False, excluded_mechanical_ids=["M2"]), catalog)
    assert all(m["type"] != "gas" and m["id"] != "M2" for m in allowed)


def test_gate_counts_add_up():
    results, gate = optimize_with_gate(_spec(budget_per_unit=200_000, target_label="nzr"))
    assert gate["evaluated"] == gate["passed"] + gate["over_budget"] + gate["missed_target"]
    assert gate["passed"] == len(results)
    assert gate["over_budget"] > 0 and gate["missed_target"] > 0


def test_empty_feasible_set_still_reports_the_gate():
    results, gate = optimize_with_gate(_spec(budget_per_unit=1))
    assert results == []
    assert gate["evaluated"] > 0 and gate["over_budget"] == gate["evaluated"]


def test_api_reports_the_gate_and_explains_an_empty_result():
    req = dict(typology="single_family", floor_area_m2=150, storeys=2, orientation="S",
               window_to_wall_ratio=0.2, target_label="code", location="Pickering (Dunbarton)")
    ok = run_optimize(OptimizeRequest(spec=ProjectSpecIn(budget_per_unit=1_000_000, **req), top_n=3))
    assert ok["gate"]["passed"] >= len(ok["results"])
    with pytest.raises(HTTPException) as err:
        run_optimize(OptimizeRequest(spec=ProjectSpecIn(budget_per_unit=1, **req)))
    assert err.value.status_code == 422 and "over budget" in err.value.detail


def test_selecting_an_excluded_system_is_refused():
    spec = ProjectSpecIn(typology="single_family", floor_area_m2=150, storeys=2, orientation="S",
                         window_to_wall_ratio=0.2, budget_per_unit=1_000_000, target_label="code",
                         mechanical_option_id="M1", excluded_mechanical_ids=["M1"])
    with pytest.raises(HTTPException):
        run_optimize(OptimizeRequest(spec=spec))


def _dev(**overrides):
    base = dict(lot_width_m=30, lot_depth_m=50, street_side="N", total_budget_cad=1_500_000,
                location="Pickering (Dunbarton)", allowed_types=["garden_suite", "three_bhk"],
                weights={"yield": 100, "cost": 0, "energy": 0, "carbon": 0})
    base.update(overrides)
    return DevSpec(**base)


def test_min_bedrooms_drops_small_types_with_a_reason():
    dev = _dev(min_bedrooms=2)
    assert [e["id"] for e in excluded_types(dev)] == ["garden_suite"]
    assert "bedroom" in excluded_types(dev)[0]["reason"]
    assert all("garden_suite" not in s.units or s.units["garden_suite"] == 0 for s in screen_dev_mixes(dev))


def test_max_storeys_drops_tall_types():
    dev = _dev(max_storeys=1)
    assert [e["id"] for e in excluded_types(dev)] == ["three_bhk"]
    assert all(s.units.get("three_bhk", 0) == 0 for s in screen_dev_mixes(dev))


def test_evaluation_rejects_an_approved_mix_with_an_excluded_type():
    _, rejected = evaluate_dev_mixes(_dev(min_bedrooms=3), [{"garden_suite": 1}])
    assert rejected and "bedroom" in rejected[0]["reason"]


def test_dev_scenarios_names_why_every_type_is_excluded():
    spec = DevSpecIn(lot_width_m=30, lot_depth_m=50, total_budget_cad=1_500_000,
                     location="Pickering (Dunbarton)", allowed_types=["garden_suite"], min_bedrooms=2)
    with pytest.raises(HTTPException) as err:
        run_dev_scenarios(DevOptimizeRequest(spec=spec))
    assert "bedroom" in err.value.detail


def test_dev_exclusions_reach_the_optimizer():
    from engine.archetypes import ARCHETYPES
    from engine.dev_optimizer import _arch_project_spec
    spec = _arch_project_spec(ARCHETYPES["garden_suite"], _dev(excluded_mechanical_ids=["M1"]))
    assert spec.excluded_mechanical_ids == ["M1"]
