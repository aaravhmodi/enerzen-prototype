"""TRL 5 validation: embodied carbon intensity (cradle to gate) of EnerZen's
catalog designs against published Canadian Part 9 home studies:

- Builders for Climate Action, EMBARC (500+ GTA Part 9 homes, 2017-2020):
  average about 191 kgCO2e/m2.
- City of Vancouver Part 9 benchmark report (BCA, 2022): 13 homes,
  138-357 kgCO2e/m2, 200 recommended benchmark.
- Nelson / Castlegar BC study: 34 homes, low about 71 kgCO2e/m2.

Proposed acceptance: inside the published range (71-357) and within 30% of
the GTA average. The cheapest passing configuration at the code and Net Zero
Ready targets, in Pickering, represents each design.
Results and discussion: docs/TRL5_VALIDATION_RESULTS.md.
"""

import pytest

from engine.archetypes import ARCHETYPES
from engine.dev_optimizer import DevSpec, _arch_project_spec
from engine.optimizer import optimize

GTA_AVERAGE = 191
PUBLISHED_RANGE = (71, 357)


def _embodied(arch_id, target):
    dev = DevSpec(lot_width_m=45, lot_depth_m=60, street_side="N", total_budget_cad=10_000_000,
                  location="Pickering (Dunbarton)", allowed_types=[arch_id], target_label=target)
    cheapest = min(optimize(_arch_project_spec(ARCHETYPES[arch_id], dev)), key=lambda r: r.construction_cost)
    return cheapest.embodied_carbon_kg_co2e_m2


SCOPE_GAP = pytest.mark.xfail(strict=True, reason=(
    "Known gap: embodied carbon covers the envelope, windows and mechanical only; the published studies "
    "also count interior partitions and intermediate floors, so 2-storey homes read about 55-60% low."))
MURB_GEOMETRY = pytest.mark.xfail(strict=True, reason=(
    "Known gap: each MURB dwelling carries the whole building's slab (see test_energy.py)."))

CASES = [
    ("garden_suite", "code"), ("garden_suite", "nzr"),
    pytest.param("three_bhk", "code", marks=SCOPE_GAP), pytest.param("three_bhk", "nzr", marks=SCOPE_GAP),
    pytest.param("townhouse", "code", marks=SCOPE_GAP), pytest.param("townhouse", "nzr", marks=SCOPE_GAP),
    ("murb", "code"), pytest.param("murb", "nzr", marks=MURB_GEOMETRY),
]


@pytest.mark.parametrize("arch_id,target", CASES)
def test_embodied_carbon_matches_published_part9_homes(arch_id, target):
    value = _embodied(arch_id, target)
    assert PUBLISHED_RANGE[0] <= value <= PUBLISHED_RANGE[1]
    assert value == pytest.approx(GTA_AVERAGE, rel=0.30)
