# EnerZen — TRL 5 Validation Plan

Status: 2026-10-08. Owner: EnerZen. Governing spec:
`EnerZen_Performance_Engine_Developer_Flowchart.docx`.

## 1. Goal

Reach Technology Readiness Level 5 as defined by Innovation, Science and
Economic Development Canada
([ISED TRL scale](https://ised-isde.canada.ca/site/innovation-canada/en/technology-readiness-levels)):

- **TRL 4 — component and/or validation in a laboratory environment:** "basic
  technological components are integrated to establish that they will work
  together."
- **TRL 5 — component and/or validation in a simulated environment:** "the
  basic technological components are integrated for testing in a simulated
  environment."

**Where EnerZen stands (2026-10-08): TRL 4, with parts of TRL 5.** The
flowchart's core engines (design catalog, assembly catalog, location and
planning data, energy, cost, carbon, construction time, lifecycle and
optimization) run as one deployed system, exercised by 59 automated tests and
a browser walkthrough of both paths. What is missing for TRL 5 is documented
evidence that each engine's numbers hold up against a recognized reference
under realistic conditions.

The level a funding program assigns is the reviewer's decision; this plan
produces the evidence they would look for.

## 2. The simulated environment

Tests run the integrated system (API end to end, not functions in isolation)
on realistic inputs:

- **Site:** Pickering (Dunbarton), Ontario — climate zone 6, NBCC 2015 snow
  loads, Pickering municipal data, and the default lot and setbacks.
- **Designs:** EnerZen's four catalog types — Garden Suite, 3-Bedroom Unit,
  MURB, Townhouse — at the sizes in `engine/archetypes.py`.
- **Targets:** code minimum, Net Zero Ready and Passive House.
- **Both paths:** Path A (one unit) and Path B (a development on the default
  30 x 50 m lot).

## 3. Validation matrix

One row per box in the flowchart's "EnerZen Core Engine". Acceptance limits
are **proposed** and should be agreed with EnerZen (and any reviewer) before
results are judged.

| Core engine | Reference | Metric | Proposed acceptance | Needs EnerZen data? | Status |
|---|---|---|---|---|---|
| Assembly catalog (R-values) | National Building Code A-9.36.2.4 parallel-path method, as tabulated by NRCan ([tables](https://natural-resources.canada.ca/energy-efficiency/energy-star/tables-calculating-effective-thermal-resistance-opaque-assemblies)) | Effective RSI of the same assembly | Within 5% | No | To run |
| Assembly catalog (EnerZen walls) | EnerZen panel drawing I500: 2x6 R-35, 2x8 R-40 effective | Effective R | Agree, or explain the method difference | Yes (decision D2) | Open |
| Energy engine | Ontario benchmarks in `data/assemblies.json` (code-built new home 130 kWh/m2/yr; existing 200) and Statistics Canada Ontario single-detached intensity | Site EUI of each design at code minimum; ordering across targets | Code-minimum EUI within 20% of the code-built benchmark; EUI falls as the target rises | No | To run |
| Carbon engine | Builders for Climate Action EMBARC study of 500+ GTA Part 9 homes (average about 191 kgCO2e/m2); Vancouver Part 9 benchmark report (13 homes, 138–357 kgCO2e/m2; 200 recommended benchmark) | Embodied carbon intensity, cradle to gate | Inside the published Part 9 range, and within 30% of the GTA average | No | To run |
| Cost engine | Garden Suite prototype actual or quoted cost | Class D hard cost | Accuracy band to agree with EnerZen | Yes | Blocked on data |
| Construction-time engine | EnerZen factory throughput and site records | Fabrication-to-close weeks | Accuracy band to agree with EnerZen | Yes | Blocked on data |
| Lifecycle engine | Hand calculation from the documented formula (METHODOLOGY section 10) | 20- and 30-year lifecycle cost | Exact to the dollar | No | Covered by tests |
| Optimization engine and gate | Constructed cases with known answers | Hard limits never violated; gate counts add up; ranking follows weights | All pass | No | Mostly covered by tests |
| Location and planning data | NBCC 2015 workbook; Pickering open data snapshot | Values match the source | Exact | No | Covered by tests |
| Site planning | Geometric invariants | Buildings inside setbacks; walkway clear of buildings; entrances and paths avoid parking | All pass | No | Covered by tests |

HOT2000 is not used: the flowchart does not name a simulator, and the existing
HOT2000-based correction (`engine/surrogate.py`) stays as it is.

## 4. Order of work

1. **No EnerZen data needed (now):** R-values against the NRCan method,
   energy against the benchmarks, carbon against the published Part 9 studies.
   Each check becomes a test in `tests/validation/` so it reruns on every
   change, and its results go in `docs/TRL5_VALIDATION_RESULTS.md`.
2. **Gather EnerZen data:** the Garden Suite prototype's costs and build
   records, factory throughput, and a decision on D2 (wall R-values).
3. **Cost and schedule checks** against that data.
4. **Evidence package:** the results document, with method, test cases,
   results against the agreed limits, and known limitations.

## 5. Evidence package (what a reviewer receives)

- This plan, with the agreed acceptance limits.
- `docs/TRL5_VALIDATION_RESULTS.md`: each check's inputs, reference, result,
  pass or fail, and the commit it ran on.
- The validation tests (`tests/validation/`) and how to rerun them.
- `docs/METHODOLOGY.md` and its known limitations.
- Two sample feasibility reports (one per path) from the validated commit.

## 6. Out of scope for TRL 5

Field testing on a real Pickering parcel and comparison with measured energy
use are TRL 6–7 activities (prototype demonstration in a relevant or
operational environment).
