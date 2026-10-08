# EnerZen — TRL 5 Validation Results

Companion to `docs/TRL5_VALIDATION_PLAN.md`. Each check lists its reference,
inputs, result against the proposed acceptance limit, and the test that
reruns it (`python -m pytest tests/validation -q`).

## Summary

| Check | Result | Status |
|---|---|---|
| R-values: engine material values vs NBC worksheets | +0.2% and +0.6% | Pass |
| R-values: engine method vs NBC method | +0.2% and +0.6% after switching to the code method (was +4.6% / +5.7%) | Pass (fixed 2026-10-08) |
| Energy: typical homes vs code-built benchmark | +2% (3-Bedroom Unit, Townhouse) | Pass |
| Energy: falls as the target rises | All four designs | Pass |
| Energy: Garden Suite vs benchmark | +50% | Outside limit; small-dwelling effect, needs a size-matched reference |
| Energy: MURB vs benchmark | −10% after the fix (was +74%) | Pass (fixed 2026-10-08) |
| Embodied carbon: Garden Suite | 140–150 kgCO2e/m2 | Pass |
| Embodied carbon: 2-storey homes | 73–87 kgCO2e/m2 vs about 191 | **Fail: scope gap, decision needed** |
| Embodied carbon: MURB | 41–44 after the geometry fix (was 239 / 452) | **Low: carbon scope gap (fix in progress)** |
| Cost, construction time | — | Blocked on EnerZen data |

## 1. Effective R-values (assembly catalog)

**Reference.** National Building Code of Canada, A-9.36.2.4 (2010 edition, as
adopted for Part 9 energy compliance), via two published City of Moncton
worksheets that apply it layer by layer:

- [MW-03](https://www5.moncton.ca/docs/bi/MW-03_Fiberglass_Batt.pdf): 2x6
  @ 16" o.c. (23% framing), RSI 3.87 (R-22) batt, 11.1 mm OSB, vinyl siding,
  12.7 mm gypsum, air films → **RSI 3.00** effective.
- [MW-02](https://www5.moncton.ca/docs/bi/MW-02_Extruded_Polystyrene_and_Fiberglass_Batt.pdf):
  as above with RSI 3.34 (R-20) batt and 12.7 mm XPS → **RSI 3.25** effective.

**Method.** The same two walls are rebuilt from the engine's material table
(`engine/materials.py`) and computed two ways: with the engine's own method,
and with the code's method using the engine's values.

| Wall | Published | Engine values, code method | Engine as built |
|---|---|---|---|
| MW-03 | 3.00 | 3.006 (+0.2%) | 3.138 (+4.6%) |
| MW-02 | 3.25 | 3.271 (+0.6%) | 3.437 (+5.7%) |

**Findings.**

1. **Material values: pass.** Framing (RSI 1.21 vs the code's 1.19), cavity
   insulation, sheathing, gypsum and air films reproduce the code worksheets
   within 1%.
2. **Calculation method: one failure against the proposed 5% limit.** The
   engine applies the parallel-path average across the whole assembly
   (framing path and cavity path each include every layer). The code
   averages only the framed layer, then adds the continuous layers in series
   ("isothermal planes"). The engine's approach gives a higher effective
   RSI, by 4.6–5.7% on these walls, so heat loss is understated by a similar
   amount. That flatters EUI and Net Zero Ready results slightly.
3. **The catalog's own 2x6 wall (WA1, no exterior insulation)** computes to
   RSI 3.32 against MW-03's 3.00 (+10.6%). Beyond the method gap, WA1 adds a
   ¾" air gap behind the cladding (a rainscreen) and ½" OSB; the worksheet has
   neither, so these walls are not identical.

**Resolved 2026-10-08.** The user approved the switch; the engine now uses the
code's method and both walls match within 1%. Original note: switching would
align the effective R-values with Part 9 compliance practice and the
flowchart's "confirm alignment with the targeted performance label", but
changes every energy result slightly (heat loss up about 5%). Not changed
without the user's agreement. When switched, the strict `xfail` on MW-02 in
`tests/validation/test_rvalues.py` turns into a failure, prompting its
removal.

**Test:** `tests/validation/test_rvalues.py`.

## 2. Energy (energy engine)

**Reference.** The code-built new-home benchmark in `data/assemblies.json`:
130 kWh/m2/yr site EUI (NRCan residential end-use intensity; CHBA Net Zero
program).

**Method.** Each of EnerZen's four designs is run in Pickering at the code
target with a gas furnace and central AC (the benchmark's typical system),
and the cheapest configuration that passes is taken as the code-built
equivalent. Separately, the cheapest passing configuration is compared across
the code, Net Zero Ready and Passive House targets.

| Design | Area per home | Code-built EUI (gas) | vs 130 | Cheapest EUI: code / NZR / Passive House (any system) |
|---|---|---|---|---|
| 3-Bedroom Unit | 163 m2 | 132.1 | +2% | 89.3 / 76.0 / 70.1 |
| Townhouse | 150 m2 | 133.0 | +2% | 90.8 / 78.1 / 72.0 |
| Garden Suite | 46 m2 | 195.0 | +50% | 145.1 / 127.8 / 121.8 |
| MURB (per home) | 65 m2 | 226.1 | +74% | 143.2 / 106.4 / 100.9 |

**Findings.**

1. **Typical-size homes: pass.** The 3-Bedroom Unit and Townhouse land within
   2% of the benchmark.
2. **Targets: pass.** Energy use falls from code to Net Zero Ready to Passive
   House for every design.
3. **Garden Suite: outside the limit, likely expected.** Fixed loads (hot
   water, appliances) spread over 46 m2 raise EUI per m2; the benchmark is
   for typical-size homes. A small-dwelling reference is needed before this
   can be judged.
4. **MURB: modelling bug.** Each dwelling (65 m2) is simulated as if it sat
   on the whole building's 19 x 18 m footprint (342 m2 of slab heat loss),
   and with the wall and roof ratios of a 2-storey house because the ratio
   table stops at 3 storeys. Apartments with shared walls should use less
   energy per m2 than a detached home, not 74% more. Path B MURB energy,
   operating cost and carbon are overstated until this is fixed.

**Resolved 2026-10-08.** The user approved the fix: a dwelling now takes an
equal share of the whole building's geometric envelope (`engine/geometry.py`),
and the MURB lands at 116.7 kWh/m2/yr (−10%). Original note: fix the MURB geometry, for example by simulating
the whole building from its footprint, storeys and height and reporting per
dwelling. This changes MURB results and, if wall and roof areas come from
geometry for every design, every design's results slightly.

**Test:** `tests/validation/test_energy.py`.

## 3. Embodied carbon (carbon engine)

**References.** Published cradle-to-gate (A1–A3) intensities for Canadian
Part 9 homes:
[Builders for Climate Action EMBARC](https://www.buildersforclimateaction.org/uploads/1/5/9/3/15931000/bfca_pbc-embarc_report-web.pdf)
(500+ GTA homes, average about 191 kgCO2e/m2);
[City of Vancouver Part 9 benchmark](https://vancouver.ca/files/cov/vancouver-part-9-home-material-emissions-benchmark-report-BCA-2022.pdf)
(13 homes, 138–357 kgCO2e/m2, 200 recommended); a Nelson and Castlegar BC
study (34 homes, low about 71 kgCO2e/m2).

**Method.** The cheapest passing configuration of each design at the code and
Net Zero Ready targets, in Pickering. Proposed acceptance: inside the
published range (71–357) and within 30% of the GTA average (134–248).

| Design | Code | NZR | Result |
|---|---|---|---|
| Garden Suite | 140 | 150 | Pass |
| 3-Bedroom Unit | 73 | 86 | Low |
| Townhouse | 75 | 87 | Low |
| MURB (per home) | 239 | 452 | High |

**Findings.**

1. **Garden Suite: pass.**
2. **Scope gap (2-storey homes about 55–60% low).** The engine counts the
   envelope (walls, roof, floor), windows and the mechanical system. The
   published studies also count interior partitions and intermediate floors.
   The cost model already includes interior partitions, so the two engines
   disagree on scope. A single-storey home is affected least, which is why
   the Garden Suite passes.
3. **MURB: high, from the same modelling bug as in section 2** (each dwelling
   carries the whole building's slab).

**Decision needed (user).** Add interior partitions and intermediate floors
to embodied carbon so the scope matches the published studies (and the cost
model). This raises embodied carbon for multi-storey designs.

**Test:** `tests/validation/test_carbon.py`.
