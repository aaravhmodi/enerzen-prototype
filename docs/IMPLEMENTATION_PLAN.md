# EnerZen — Implementation Plan and Hand-off

Status: 2026-10-08, after commit `9bacda1`. Governing spec:
`EnerZen_Performance_Engine_Developer_Flowchart.docx` (repo root).

This file is the hand-off for any session that continues the work, including
a cloud session. Read sections 1–3 before changing anything, then start at
section 5 ("Next up").

## 1. Working rules

- **The flowchart governs.** Build what it describes. Before a change that
  deviates from it, extends it, or changes engine results in a way the user
  has not decided, stop and ask the user.
- **Keep the methodology in sync.** Any engine or data change updates
  `docs/METHODOLOGY.md` prose in the same commit, and regenerates the PDF with
  `python docs/generate_pdf.py` (the PDF is gitignored; regenerating checks
  the Markdown renders).
- **Commit often, push to `main`.** Never add Claude or AI attribution
  (no `Co-Authored-By` lines) to commit messages. Pushing to `main`
  deploys: Vercel auto-builds `enerzen-api` (FastAPI, repo root) and
  `enerzen-prototype` (Next.js, `web/`).
- **Honest numbers.** Every default names its source or is labelled an
  EnerZen assumption. Never present a placeholder as data. Copy in the UI
  (including the "exploring" narration) only describes what the engine
  really does, in the order it does it.
- **`.gitignore` ignores `*.md` and `*.pdf`.** Tracked Markdown files were
  force-added; a new Markdown file needs `git add -f`.
- **Next.js here is a newer version than most training data.** Read
  `web/AGENTS.md` and `web/node_modules/next/dist/docs/` before using
  framework APIs.
- No 3D or elevations yet; unit designs are still in progress (Garden Suite is
  the prototype).

## 2. Run and verify

```
pip install -r requirements.txt               # API + engine
python -m uvicorn api.main:app --port 8001     # API
cd web && npm install && npm run dev           # web, http://localhost:3000
```

`web/.env.local` sets `NEXT_PUBLIC_API_URL=http://localhost:8001` (default).

Before every push:

```
python -m pytest tests -q                      # 38 tests at 9bacda1
cd web && npx tsc --noEmit && npm run lint && npm run build
```

Lint has two known warnings (`<img>` in the two site-plan views); no errors.

Browser walkthrough (both paths, validation, phone overflow, reduced motion;
POSTs are stubbed):

```
npx playwright install chromium                # once
PLAYWRIGHT_MODULE=$(npm root -g)/playwright node scripts/verify_experience.cjs
```

Set `PLAYWRIGHT_CHANNEL=msedge` on Windows to use Edge instead of the bundled
Chromium.

## 3. Repo map

- `engine/` — calculation core. `optimizer.py` (configurations, gate, Pareto
  and weighted ranking, `baseline_cost`), `dev_optimizer.py` (Path B:
  `screen_dev_mixes`, `evaluate_dev_mixes`), `soft.py` (Class D soft costs and
  soft timeline), `archetypes.py` (catalog types), `site.py`,
  `site_geometry.py`, `multi_site.py`, `svg_kit.py` (site plans),
  `report.py` (PDF), `municipal.py` + `data/pickering.json` (pilot data).
- `api/main.py` — FastAPI endpoints: `/optimize`, `/site-plan`, `/report`,
  `/dev-scenarios`, `/dev-optimize`, `/dev-site-plan`, `/locations/...`,
  `/archetypes`.
- `web/src/app/page.tsx` — screens and flow state for both paths;
  `web/src/components/` — wizard (`WizardChrome`, `ProjectForm`, `DevForm`),
  results (`ResultsPanel`, `DevScenarioReview`, `DevRecommendation`,
  `DevResults`), site plans (`SitePlanView`, `MultiSitePlanView`),
  `ExploringStage` (narrated loading); styles in `web/src/app/experience.css`.
- Reference drawings in the repo root (PDFs and DWGs are gitignored and only
  exist on the user's laptop): Garden Suite, MURB, panel details, a land
  development deck.

## 4. Decisions

| # | Topic | Decision | Status |
|---|-------|----------|--------|
| D1 | MURB size | Match the drawings: 5 storeys (G+4), 4 units/floor = 20 homes, 19 x 18 m | Done (`3e60957`) |
| D2 | Wall R-values | Panel drawing says R-35 (2x6) / R-40 (2x8) effective with 2" exterior mineral wool; engine computes R-28.4 / R-33.9 at 2" | **Open.** User unsure; walls unchanged. Do not change without the user |
| D3 | Path B order | Follow the flowchart: site plan + review first, then performance optimization | Done (`369ed90`) |
| D4 | Resilience | Deferred by the user | Options kept in Phase 4 |
| D5 | Soft costs / timeline | Published defaults, sourced in METHODOLOGY 6.9 | Done (`15c9ba0`) |

## 5. Next up

### Phase 1 — Hard constraints and gate breakdown (not started)

Flowchart: "Only solutions satisfying the hard constraints proceed."
The user has agreed to this phase.

Engine:
- `ProjectSpec` (`engine/optimizer.py`): add
  `excluded_mechanical_ids: list[str]` (default empty). Apply it where
  `mech_options` is built in both `optimize` and `baseline_cost`. Keep
  `allow_gas`.
- Gate breakdown: in the `optimize` loop, count configurations evaluated,
  rejected over budget (`total_cost > spec.budget_per_unit`) and rejected for
  missing the target (`target_performance_passes`). Add
  `optimize_with_gate(spec, weights) -> (results, gate)` and keep `optimize`
  returning results only, so existing callers are unchanged.
- `Archetype` (`engine/archetypes.py`): add `bedrooms` — Garden Suite 1,
  3-Bedroom Unit 3, Townhouse 3, MURB 1 (its units are 1- and 2-bed per
  `MURB.pdf`, so 1 is the guaranteed minimum). Include it in
  `archetype_list()`.
- `DevSpec` (`engine/dev_optimizer.py`): add `min_bedrooms`, `max_storeys`
  and `excluded_mechanical_ids`. `screen_dev_mixes` drops types that fail
  them and reports each dropped type with a reason; pass exclusions into
  `_arch_project_spec`.

API (`api/main.py`):
- `/optimize` returns `gate: {evaluated, passed, over_budget, missed_target}`;
  when nothing passes, the 422 message includes that breakdown.
- `/dev-scenarios` returns `excluded_types: [{id, reason}]`; when every type
  is excluded, a 422 names why.
- Add the new fields to `ProjectSpecIn` and `DevSpecIn`.

Web:
- Path A Brief: "Minimum bedrooms". The Design step shows which catalog
  designs meet it; a custom brief is labelled "bedrooms not verified" (the
  engine has no bedroom model for custom geometry).
- Path A Systems: checkboxes to exclude specific mechanical systems.
- Path B Typology: minimum bedrooms, maximum storeys and excluded systems; the
  review screen lists excluded types with their reason.
- Path A results toolbar: "N evaluated · M passed · X over budget · Y missed
  the target".
- Update `web/src/lib/api.ts` types.

Tests: each constraint rejects what it should; gate counts add up
(`evaluated = passed + over_budget + missed_target`); an empty feasible set
returns the breakdown. Update METHODOLOGY section 11.2.

### Phase 2 — Nine-section feasibility report, both paths (not started)

The user has agreed to this phase. Restructure `engine/report.py` to the
flowchart's sections, and add a Path B report.

1. Executive feasibility, with status rules:
   FEASIBLE (top option passes every hard constraint and gate),
   FEASIBLE WITH MODIFICATIONS (passes only after a relaxed constraint, which
   is named), FURTHER STUDY REQUIRED (no parcel/zoning check, a site-fit
   failure, or a data gap). While no Pickering parcel is selected, zoning is
   always "not checked", so say so plainly rather than claiming feasibility.
2. Recommended solution: Path A design and systems; Path B mix, site plan and
   green-space strategy. No 3D.
3. Capital cost, Class D: hard + soft (`engine/soft.py`).
4. Timeline: soft (`soft_timeline`) + hard (build schedule).
5. Energy: EUI, target vs achieved, PV generation.
6. Carbon: embodied + operational = lifecycle, kgCO2e/tCO2e first.
7. Lifecycle economics, with savings against the code-built benchmark in
   `data/assemblies.json` (`benchmarks`).
8. Priority achievement: for each weighted objective, where the recommended
   option ranks among the feasible set.
9. Next steps, driven by what is unchecked (zoning not checked → municipal
   pre-consultation; soil defaults → geotechnical report; and so on), with
   enhancements listed separately.

Path B: add `/dev-report` (spec + approved mix → PDF) and a "Download
feasibility report" button on the recommendation screen. Embedding the site
plan needs an SVG renderer in reportlab (`svglib` is not a dependency);
either add it to `requirements.txt` (check Vercel bundle size) or describe
the plan in text. Ask the user if unsure.

Tests: each status rule; every section present for both paths. Update
METHODOLOGY.

### Phases after that

- **Phase 3, Path B remainder** (reorder done): planning inputs (parkland or
  green-space share, amenity space, density/unit caps) drawn and checked on
  the plan; geothermal and storage need catalog data (ask the user for
  sources); let the user move, swap or remove buildings between review
  iterations.
- **Phase 4, resilience (deferred).** Options researched: hours of safety
  to 12 C (LEED IPpc100's 54 F floor, 4-day outage), to 4.4 C (RMI's 40 F
  line), or LEED's 7-day degree-hour test. Needs NBCC January design
  temperatures in the location data. Do not start without the user.
- **Phase 5, compliance integration point:** a `ComplianceCheck` interface
  (pass / fail / not checked, with reasons) between performance calculations
  and optimization, no-op by default.
- **Phase 6, Pickering pilot parcel:** when the address is known, pull parcel
  geometry, zoning and pre-consultation records; replace assumed lot
  dimensions.

## 6. Done so far (2026-10-07 to 10-08)

- Minimal, animated UI; staged wizards for both paths; narrated
  "exploring" screen; results revealed over about three seconds (`df005da`,
  `5b79222`).
- Pickering city-wide data and multifamily energy benchmark (`e29d5f2`,
  `3b31bdc`).
- Site plans redrawn: walkway through clear corridors, rear shared garden,
  street-facing entrances with paths, MURB corridor/core/balconies, townhouse
  party walls (`5b79222`, `30d3341`).
- MURB sized to the drawings (`3e60957`); Class D soft costs and soft
  timeline (`15c9ba0`); Path B reordered to the flowchart, and a MURB now
  counts all 20 of its homes (`369ed90`).
- Phone layout fixed across all screens (`9bacda1`).

## 7. Known limitations

- Path B ranking runs the optimizer once per housing type: about 7 s on the
  deployed API.
- The MURB footprint is scaled from the PDF; confirm against the DWG.
- Concept renders need an OpenAI key; without it the vector plan is shown
  alone.
- The exploring screen's narration advances on a timer; the API returns a
  single response, not live progress (a follow-up could stream stages).
