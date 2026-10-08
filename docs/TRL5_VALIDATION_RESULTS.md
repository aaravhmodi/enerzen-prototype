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
| Embodied carbon: 2-storey homes | 78–96 kgCO2e/m2 vs about 189 (after adding interior walls and floors) | **Below the reference: partly expected (no basements); material factors to audit** |
| Embodied carbon: MURB | 49 per home (was 239 / 452 before the geometry fix) | **Low: no shared structure modelled** |
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
(503 as-built GTA homes; weighted average 189 kgCO2e/m2 of heated floor area,
154 of total floor area);
[City of Vancouver Part 9 benchmark](https://vancouver.ca/files/cov/vancouver-part-9-home-material-emissions-benchmark-report-BCA-2022.pdf)
(13 homes, 138–357 kgCO2e/m2, 200 recommended); a Nelson and Castlegar BC
study (34 homes, 72–309, average 150).

**EMBARC scope.** Included: footings and slabs, foundation walls, posts and
beams, exterior and party walls, cladding, windows, interior walls, floors,
ceilings, roof. Excluded: mechanical, electrical and plumbing, millwork,
stairs, doors, surface finishes; biogenic storage in lumber excluded.
Concrete in foundation walls, slabs and footings is 33% of the total.

**Method.** The cheapest passing configuration of each design at the code and
Net Zero Ready targets, in Pickering. Proposed acceptance: inside the
published range (71–357) and within 30% of the GTA average.

| Design | Code | NZR | Result |
|---|---|---|---|
| Garden Suite | 143 | 177 | Pass |
| 3-Bedroom Unit | 78 | 96 | Below the reference |
| Townhouse | 80 | 93 | Below the reference |
| MURB (per home) | 49 | 49 | Below the published range |

(After the 2026-10-08 fixes: building-code R-values, MURB geometry, and
interior walls and intermediate floors added to the carbon scope.)

**Findings.**

1. **Garden Suite: pass.**
2. **Scope additions were small.** Interior walls and intermediate floors,
   which EMBARC counts and the engine did not, add 4–8 kgCO2e/m2. An earlier
   version of this document attributed the whole shortfall to them; that was
   wrong.
3. **2-storey homes sit about half the GTA average.** Part of this is
   expected: EnerZen designs are slab-on-grade with no basement, while
   foundation concrete is a third of EMBARC's total. Removing it from the
   reference gives roughly 127 kgCO2e/m2, still above the engine's 78–96. The
   remainder points to material carbon factors (for example ½" gypsum at
   1.3 kgCO2e/m2 looks low against typical EPDs) and elements the engine
   does not model (posts and beams, party walls).
4. **MURB below the range.** A dwelling's share of the envelope is small, and
   the engine has no shared structure (stairs, corridors, elevator core,
   party walls).

**Next steps.** Audit `engine/materials.py` carbon factors against BEAM or
product EPDs; add party walls for townhouses and MURBs and the MURB's shared
structure; then agree a no-basement reference with EnerZen so the
comparison is like for like. These change results, so they need the user's
agreement.

**Test:** `tests/validation/test_carbon.py`.
