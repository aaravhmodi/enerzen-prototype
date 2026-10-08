"""TRL 5 validation: site EUI of EnerZen's catalog designs against the
code-built Ontario benchmark in data/assemblies.json (130 kWh/m2/yr for a new
code-built home; NRCan residential end-use intensity, CHBA Net Zero program).

A code-built home is represented by the cheapest code-passing configuration
with a gas furnace (the benchmark's typical heating system), in Pickering.
Results and discussion: docs/TRL5_VALIDATION_RESULTS.md.
"""

import pytest

from engine.archetypes import ARCHETYPES
from engine.dev_optimizer import DevSpec, _arch_project_spec
from engine.optimizer import load_catalog, optimize

CODE_BUILT_EUI = load_catalog()["benchmarks"]["eui_kwh_m2_yr"]["code_built_new"]


def _spec(arch_id, target="code", mechanical=None):
    dev = DevSpec(lot_width_m=45, lot_depth_m=60, street_side="N", total_budget_cad=10_000_000,
                  location="Pickering (Dunbarton)", allowed_types=[arch_id], target_label=target)
    spec = _arch_project_spec(ARCHETYPES[arch_id], dev)
    spec.mechanical_option_id = mechanical
    return spec


def _cheapest(spec):
    return min(optimize(spec), key=lambda r: r.construction_cost)


SMALL_UNIT = pytest.mark.xfail(strict=True, reason=(
    "Garden Suite (46 m2) is about 50% above a benchmark set for typical-size homes; fixed hot-water "
    "and appliance loads spread over a small floor area raise EUI. Needs a small-dwelling reference."))
@pytest.mark.parametrize("arch_id", [
    "three_bhk", "townhouse",
    pytest.param("garden_suite", marks=SMALL_UNIT),
    "murb",
])
def test_code_built_eui_within_twenty_percent_of_the_benchmark(arch_id):
    eui = _cheapest(_spec(arch_id, "code", mechanical="M1")).eui_kwh_m2_yr
    assert eui == pytest.approx(CODE_BUILT_EUI, rel=0.20)


@pytest.mark.parametrize("arch_id", list(ARCHETYPES))
def test_energy_use_falls_as_the_target_rises(arch_id):
    euis = [_cheapest(_spec(arch_id, target)).eui_kwh_m2_yr for target in ("code", "nzr", "passive_house")]
    assert euis[0] > euis[1] > euis[2]
