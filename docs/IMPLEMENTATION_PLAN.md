# EnerZen — Implementation Plan to Close the Flowchart Gaps

Status: updated 2026-10-08. Governing spec:
`EnerZen_Performance_Engine_Developer_Flowchart.docx`.

Decisions so far: D1 done (MURB is 5 storeys, 20 units, 19 x 18 m). D2 open
(user unsure; walls unchanged). D3 done (Path B follows the flowchart order).
D4 awaiting confirmation of the proposed definition. D5 done with published
defaults (METHODOLOGY 6.9).

## Where the app stands

Built and matching the flowchart: landing → path select; Path A five-step
brief (inputs, site, design, systems, priorities); Path B five-step brief with
a three-iteration review loop; shared core engine (catalog, assemblies,
location, energy, cost, carbon, schedule, lifecycle, Pareto + weighted
optimizer); performance gate (budget, NZR threshold); 2D site plans with
walkway, parking, shared green, street-facing entrances and archetype detail;
Pickering city-wide data; Path A PDF report.

## 1. Decisions needed first

These change engine results, so they need your answer before any code.

| # | Question | What the references show | What the engine does today |
|---|----------|--------------------------|----------------------------|
| D1 | MURB storeys and footprint | `MURB.pdf` scales to roughly 19 x 18 m with 4 units/floor; the DWG is named "G+4" (5 storeys) | 6 storeys, 24 units, 20 x 15 m |
| D2 | Wall R-values | `PANEL DETAILS.pdf`: 2x6 wall R-35 effective, 2x8 wall R-40 effective, each with 2" exterior mineral wool, fibre cement, 1" rainscreen, 1.5" service cavity; 2x8 uses dense-pack cellulose | Same walls compute to R-28.4 (2x6) and R-33.9 (2x8) at 2" exterior wool; the engine sweeps 0/2/4" and uses vinyl siding and mineral-wool batts |
| D3 | Path B order | Flowchart: site plan + user feedback, *then* building performance optimization | Each type's envelope is optimized first, then mixes are tested and the plan drawn |
| D4 | Resilience | Flowchart lists it as a weighted priority | Not modelled; needs a definition (see Phase 4) |
| D5 | Class D soft costs and soft timeline | Report section 3/4 require them | No data; needs EnerZen allowances or agreed defaults |

For D2, the drawing's R-values may be clear-wall or nominal figures rather than
parallel-path effective values. Confirm which, and whether to rebuild WA1/WA2
to match the drawing's layers exactly.

## 2. Phases

Each phase ends with tests, a METHODOLOGY.md update and a PDF regeneration.

### Phase 1 — Hard constraints vs soft priorities (Path A, then B)

Flowchart: "Only solutions satisfying the hard constraints proceed."

- Inputs: add bedrooms (minimum), maximum storeys and prohibited systems
  (a generalization of today's "allow gas") to the Brief and Systems steps.
- Engine: one `HardConstraints` object checked in the gate
  (`engine/optimizer.py`), reporting *why* each configuration failed.
- UI: the results screen says how many configurations each gate rejected
  ("38 over budget, 12 missed the NZR threshold").
- Tests: each constraint rejects what it should; an empty feasible set returns
  the failure breakdown instead of a bare 422.

### Phase 2 — Standardized feasibility report (both paths)

Restructure `engine/report.py` to the flowchart's nine sections and add a
Path B report endpoint.

1. Executive feasibility with status rules:
   FEASIBLE (top option passes every hard constraint and gate),
   FEASIBLE WITH MODIFICATIONS (passes only after a relaxed constraint, which is named),
   FURTHER STUDY REQUIRED (no parcel/zoning check, a site-fit failure, or a data gap).
2. Recommended solution: Path A design and systems; Path B 2D plan, mix and
   amenity strategy. 3D stays out of scope until unit designs are ready.
3. Capital cost, labelled Class D, with hard costs and soft costs (needs D5).
4. Timeline: hard (fabrication to envelope close, existing) and soft (needs D5).
5. Energy performance: EUI, target vs achieved, PV generation.
6. Carbon: embodied + operational = lifecycle, in kgCO2e/tCO2e first.
7. Lifecycle economics, plus savings against the code-built baseline.
8. Priority achievement: target vs predicted for each weighted objective.
9. Next steps: professionals and studies, driven by what is unchecked
   (for example, zoning not checked → municipal pre-consultation).

### Phase 3 — Path B to flowchart (reorder done 2026-10-08; planning inputs and renewables remain)

- Reorder per D3: brief → planning → typology/mix → **site plan → feedback (≤3)**
  → building performance optimization for the chosen mix → development
  calculations → ranking.
- Planning inputs: parkland/green-space share, community or amenity space,
  and density/unit-cap constraints, each drawn on the site plan and checked.
- Renewables: PV now; geothermal and storage need catalog entries (cost,
  performance, carbon). Data source to confirm.
- Feedback loop: the user can move, swap or remove buildings between
  iterations; the engine re-validates fit and setbacks each time.

### Phase 4 — Resilience priority

Proposed definition for review: passive survivability, meaning hours a home
stays above a safe indoor temperature in a winter outage. Derived from the
envelope UA and thermal mass the engine already computes, plus a backup-power
credit when storage is selected. Adds a fifth weight to both paths.

### Phase 5 — Compliance integration point

Flowchart: reserve a deterministic compliance gate between performance
calculations and optimization.

- Add a `ComplianceCheck` interface with a pass/fail/not-checked result and
  reasons; ship a no-op default so behaviour is unchanged.
- First real check: Pickering zoning (setbacks, height, permitted use) once a
  pilot parcel is chosen. Today it reports "not checked".

### Phase 6 — Pickering pilot parcel

When the pilot address is known: pull parcel geometry, zoning and any
pre-consultation records; replace assumed lot dimensions; show the parcel in
the site plan.

## 3. Smaller follow-ups

- Live progress: stream real engine stages (server-sent events) so the
  exploring screen can show actual progress instead of timed narration.
- Rename "Ranked by total units, then energy efficiency" in the Path B table;
  ranking now follows the user's weights.
- MURB and townhouse rows: consider stacked/attached unit counts in the
  parking ratio once Phase 3 planning inputs exist.

## 4. Suggested order

D1–D5 answers → Phase 1 → Phase 2 → Phase 3 → Phase 5 → Phase 4 → Phase 6
(when a parcel exists). Phases 1 and 2 are the most visible improvement for
the pilot; Phase 3 is the largest change.
