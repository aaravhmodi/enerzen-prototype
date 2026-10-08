# EnerZen — TRL 5 Validation Results

Companion to `docs/TRL5_VALIDATION_PLAN.md`. Each check lists its reference,
inputs, result against the proposed acceptance limit, and the test that
reruns it (`python -m pytest tests/validation -q`).

## Summary

| Check | Result | Status |
|---|---|---|
| R-values: engine material values vs NBC worksheets | +0.2% and +0.6% | Pass |
| R-values: engine method vs NBC method | +4.6% and +5.7% (limit 5%) | **Fail on one case: known gap, decision needed** |
| Energy vs Ontario benchmarks | — | To run |
| Embodied carbon vs published Part 9 studies | — | To run |
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

**Decision needed (user).** Switching the engine to the code's method would
align the effective R-values with Part 9 compliance practice and the
flowchart's "confirm alignment with the targeted performance label", but
changes every energy result slightly (heat loss up about 5%). Not changed
without the user's agreement. When switched, the strict `xfail` on MW-02 in
`tests/validation/test_rvalues.py` turns into a failure, prompting its
removal.

**Test:** `tests/validation/test_rvalues.py`.
