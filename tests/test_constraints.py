from engine.optimizer import ProjectSpec, allowed_mechanical, load_catalog, optimize


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
