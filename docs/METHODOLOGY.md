# EnerZen Performance Engine — Methodology

Generated {{DATE}} · source of truth: `docs/METHODOLOGY.md` · regenerate with `python docs/generate_pdf.py`

This document describes every calculation the engine performs, at the level of the
underlying formulas and constants. It is written to be auditable: each section
names the source file so a reader can check the maths against the code.

---

## 1. Assumptions and limitations

These are the things a reader should know before trusting a number from this
tool.

**The energy model is simplified.** A steady-state degree-day method ignores
thermal mass, hourly weather, real shading geometry, part-load equipment
behaviour and distribution losses. It is not HOT2000 and is not a compliance
tool. It is calibrated against NRCan end-use shares, with heating as the dominant
end use, and is compared directionally with the catalog's approximate Ontario
benchmarks (200 kWh/m2/yr existing and 130 kWh/m2/yr code-built new).

**Material cost and carbon values are defaults.** R-values per inch come from
published tables and the effective-R method cross-checks well against NRCan
(the National Building Code method reproduces published wall worksheets within 1%). But
the *cost* and *embodied carbon* per material are default ranges, not EnerZen's
procurement data, and should be replaced before quoting.

**Geometry is partly explicit.** Footprint length and width are entered, and
conditioned floor area is their product times the storey count. Foundation area,
perimeter and quantities use those dimensions. Wall and roof areas still come
from typical residential floor-area ratios rather than designed elevations and
roof geometry. A 2.7 m storey height converts total floor area to air volume.

**Cost is itemized but rates are defaults.** The old 1200 CAD/m2 blanket is
gone; every line (connections, partitions, finishes, mechanical, fit-out,
contingency) is explicit, but the unit rates are published Canadian defaults
awaiting EnerZen procurement data. Window and mechanical installation labour is
still omitted. Fit-out and services remain a single 650 CAD/m2 lump.

**The thickness sweep is coarse.** Insulation is optimised over a few discrete
thicknesses, not a continuous range, to keep the search fast.

**Build time covers factory fabrication and site work to envelope close only.**
The 30-panels-per-week production rate and one-week setup are defaults awaiting
EnerZen factory data; the result is not a project schedule.

**Cooling is glazing-driven only**, and uses a hard-coded COP of 3.5 rather than
the selected mechanical system's rating.

**Lifecycle cost omits maintenance and replacement**, which will understate the
true cost of any system over its study period.

**Climate zone and region are auto-classified.** Each of the 227 Ontario
locations is assigned a zone (6/7a/7b) and utility region by a city-name
classifier, overridable per project. Snow load (Ss/Sr) is real, from the NBCC
2015 workbook; soil values are conservative regional defaults, not a site
investigation.

**Benchmarks and rates are provincial/regional averages** from secondary
sources, adequate for directional comparison in a prototype.

**The Monte Carlo distributions are engineering judgement**, not calibrated
against measured EnerZen data — a structured confidence estimate, not a
validated statistic.

**Site placement is rule-based, not a planning-compliance check.** The
placement engine (section 14) applies passive-solar siting heuristics and the
lot dimensions/setbacks the user supplies; it does not consult municipal
zoning bylaws, real parcel geometry, easements, tree cover or grading, and its
output is not a substitute for a survey or a site plan approval. No suitable
open dataset pairing real parcel geometry with energy-efficient siting
outcomes was found during development (see the project's site-plan research
notes), so this section's rules are derived from published passive-solar
design guidance rather than fitted to Ontario-specific data.

**Pickering data is city-wide context, not a site review.** The pilot snapshot
(section 5.3) adds municipal inventories and a small multifamily energy
benchmark. No pilot parcel is selected, so zoning, setbacks and permitted uses
are not checked.

---

## 2. What the engine does

The engine takes a project description and searches for the best assembly
configuration. It is a deterministic physics-and-costing model — there is no
machine learning anywhere in it.

The Streamlit interface is organised as a project brief followed by five levels
of decision detail: recommendation, selected systems, viable alternatives,
performance and cost/energy trade-offs. Technical quantities remain behind
clearly labelled disclosure panels so the primary result is readable without
hiding the assumptions needed for audit.

Short-choice inputs are shown directly rather than hidden in dropdowns; selects
are reserved for long catalogs such as Ontario locations and solar packages.
Interaction colors use semantic roles (primary, selected, hover, focus,
success, warning, error and disabled). Selected states use a restrained sage
surface with dark text, while keyboard focus uses a separate high-contrast
yellow outline so selection and focus are never communicated by the same cue.
The interface uses one sans-serif family stack across headings, body copy,
metrics, controls, tables and chart labels. Weight, size and spacing establish
hierarchy; typeface changes do not. The Streamlit theme, custom controls and
Altair charts share the same neutral, primary and semantic color tokens.

After optimization, both paths can generate a nine-section feasibility report
as a PDF (section 15). It states a feasibility status from explicit checks,
then the recommended solution, Class D capital cost, timeline, energy, carbon,
lifecycle economics against a code-built benchmark, how the recommendation
ranks on each priority, and the next steps the unchecked items call for. The
report is a decision summary; it explicitly does not represent a permit,
tender, structural design or professional geotechnical opinion.

The search is exhaustive. The catalog holds 5 wall panels, 3 roof cassettes,
2 floor cassettes, 3 window packages and 3 mechanical systems, so the engine
evaluates every combination:

```
5 x 3 x 2 x 3 x 3 = 270 candidate configurations
```

For each candidate it runs five independent calculation modules, discards any
that breach the budget (or the performance target), and ranks the survivors.

```
Project inputs
      |
      v
  For each of 270 combinations:
      |-- simulator.py : energy demand, EUI, EnerGuide, NZR probability
      |-- cost.py      : construction cost, build schedule
      |-- carbon.py    : embodied + operational carbon
      |-- solar.py     : PV generation, cost, carbon
      |-- finance.py   : monthly utility bill, 30- and 20-year lifecycle cost
      |
      v
  Filter (budget, target label)
      |
      v
  Rank (Pareto dominance, then weighted score)
      |
      v
  Ranked list of configurations
```

### Inputs

| Input | Meaning |
| --- | --- |
| Building type | single family, townhouse, or MURB |
| Floor area | conditioned floor area, m2 |
| Storeys | 1, 2 or 3 — selects the surface-area ratios |
| Climate zone | 6, 7a or 7b — selects degree days and thresholds |
| Orientation | main facade direction; drives solar gain and PV yield |
| Window-to-wall ratio | fraction of wall area that is glazing |
| Performance target | code / NZR / Passive House — sets the airtightness target |
| Solar option | rooftop PV array size |
| Budget per unit | hard constraint; configurations above it are discarded |
| Priority weights | cost / speed / carbon / energy, used for final ranking |

### Outputs

Optimized assembly selection, construction cost, build time, embodied carbon,
operational energy, EnerGuide estimate, Net Zero Ready probability, lifecycle
cost, and a monthly utility estimate.

---

## 3. Energy model

Source: `engine/simulator.py`

A steady-state **degree-day heat balance**. The governing idea: heat escapes a
building in proportion to how leaky its surfaces are multiplied by how cold it is
outside, over the whole heating season.

This is a simplified stand-in for HOT2000. The module is designed so it can be
replaced by a HOT2000 wrapper without changing its interface.

### 3.1 Surface areas

Source: `engine/geometry.py`, the single source the energy, cost, schedule and
carbon models share.

**Homes of 1–3 storeys** use fixed ratios to floor area for walls and roof.
These are generic residential forms, not EnerZen's actual designed units. The
slab is the footprint when one is given.

| Storeys | Wall ratio | Roof ratio | Floor ratio |
| --- | --- | --- | --- |
| 1 | 1.80 | 1.05 | 1.00 |
| 2 | 1.40 | 0.55 | 0.52 |
| 3 | 1.20 | 0.40 | 0.38 |

```
wall_area        = floor_area x wall_ratio
roof_area        = floor_area x roof_ratio
floor_area_surf  = footprint, or floor_area x floor_ratio
window_area      = wall_area x window_to_wall_ratio
opaque_wall_area = wall_area - window_area
```

**Multi-unit buildings, and buildings taller than the ratio table,** are
measured from their geometry, and one dwelling takes an equal share of the
whole building's envelope:

```
wall_area  = 2 x (length + width) x storeys x 2.7 m / dwellings
roof_area  = slab_area = length x width / dwellings
```

For the MURB (19 x 18 m, 5 storeys, 20 homes) each 65 m2 apartment carries
50 m2 of wall and 17 m2 each of roof and slab. Until 2026-10-08 each MURB
apartment was simulated on the whole 342 m2 slab with 2-storey ratios, which
put its energy use 74% above the code-built benchmark; it now sits 10% below
it, as expected for an apartment with shared walls
(`tests/validation/test_energy.py`).

### 3.2 Heat loss coefficient (UA)

UA is the rate of heat loss per degree of temperature difference, in watts per
kelvin (W/K). For each opaque or glazed surface it is area multiplied by the
assembly U-value (U is the inverse of R — lower U means better insulation).

```
UA_wall    = opaque_wall_area x wall_U
UA_roof    = roof_area        x roof_U
UA_floor   = floor_area_surf  x floor_U
UA_windows = window_area      x window_U
```

Air leakage is handled separately. A blower-door test reports ACH50 (air changes
per hour at 50 pascals of pressure). Real-world infiltration is far lower than
the test condition; the model uses the standard **divide-by-20 rule of thumb**,
corrected for how exposed the site actually is to wind:

```
shielding       = SHIELDING_MULTIPLIER[terrain_exposure]
ACH_natural     = ACH50 x shielding / 20
volume          = total_conditioned_floor_area x 2.7
UA_infiltration = ACH_natural x volume x 0.33
```

- `2.7` is the assumed storey height in metres.
- `0.33` is the volumetric heat capacity of air in Wh/(m3.K).
- The plain divide-by-20 rule is itself an approximation of what a detailed
  wind/stack infiltration model produces for an "average" site — it doesn't
  vary with how exposed or sheltered a building actually is. NRCan's HOT2000
  (the AIM-2 infiltration model) documents roughly a 2.5x spread in natural
  infiltration across its shielding-class range (1 = very exposed site, 8 =
  heavily sheltered) for the same blower-door result, driven by wind
  speed/pressure differences at the site. `terrain_exposure` applies that
  documented spread as a per-location multiplier: `urban` 0.75 (dense city
  core — heavy shielding from neighbouring buildings), `suburban` 1.00 (a
  typical subdivision — this is the model's original calibration point, so
  this setting reproduces the un-corrected divide-by-20 result exactly),
  `rural` 1.35 (small town / open lot edges), `exposed` 1.65 (open farmland,
  near-shore, far north). It's assigned per region (`data/assemblies.json →
  regions`), not per site — a real improvement over ignoring wind exposure
  entirely, but still a coarse default rather than a site-specific value.
  Source: "Implementation of the AIM-2 Infiltration Model in HOT2000"
  (NRCan/CMHC).

A heat recovery ventilator (HRV) reclaims heat from exhaust air, so only the
unrecovered fraction counts:

```
UA_vent  = UA_infiltration x (1 - hrv_efficiency)
UA_total = UA_wall + UA_roof + UA_floor + UA_windows + UA_vent
```

### 3.3 Gross heat loss and internal gains

Heating demand is gross conduction/infiltration loss **less** the useful heat
already generated inside the building. An earlier version ignored gains and used
a crude `solar_factor` multiplier, which over-predicted heating badly.

```
gross_loss = UA_total x HDD x 24 / 1000        (kWh/yr)
```

**Internal gains** — heat from appliances, occupants and hot-water losses, all of
which end up warming the house during the heating season:

```
gain_internal = appliances x 0.90 x season_fraction
              + hot_water  x 0.20 x season_fraction
              + occupants  x 100 W x 0.60 x season_hours / 1000
```

- `0.90` — fraction of appliance/lighting energy released as heat.
- `0.20` — tank and pipe losses from hot water released indoors.
- `100 W` — sensible heat per occupant (ASHRAE); `0.60` presence fraction.
- `season_fraction` — heating-season days / 365 (zone-dependent, 230-270 days).

**Solar gains** — passive gain through glazing, distributed across facades by
orientation and priced by each facade's seasonal vertical irradiance:

```
gain_solar = sum over facades of
             window_area x facade_fraction x frame_factor x SHGC
             x irradiance[facade] x shading
```

| Facade | Seasonal irradiance (kWh/m2) |
| --- | --- |
| South | 450 |
| East / West | 260 |
| North | 160 |

**Net heating**, then purchased energy after mechanical efficiency:

```
useful_gains  = 0.90 x (gain_internal + gain_solar)
heating_net   = max(0, gross_loss - useful_gains)
heating_purch = heating_net / (COP x cop_factor)
```

- `0.90` — utilisation factor: in a cold-climate heating season almost all gains
  are useful.
- **COP** — plant coefficient of performance. A heat pump at COP 2.5 delivers 2.5
  kWh of heat per kWh electricity; a gas furnace is 0.92 (combustion losses).

### 3.4 Cooling demand

Cooling is modelled as solar gain through glazing only — a heavy simplification
appropriate to the modest Canadian cooling season.

```
cooling = window_area x SHGC x CDD x 24 / 1000 x 0.4 / 3.5
```

`0.4` is an empirical driving fraction; `3.5` is an assumed cooling COP.

### 3.5 Base loads

Scaled to derived occupancy, calibrated against NRCan end-use shares (space
heating ~61%, water heating ~18%, appliances/lighting ~21% of Canadian
residential energy).

```
occupants  = max(1, 1 + floor_area / 75)      (~3.0 for a 150 m2 home)
hot_water  = occupants x 1800                 (kWh/yr)
appliances = 1500 + 20 x floor_area           (kWh/yr)
```

An earlier version divided hot water by storey count, which had no physical basis
and ran roughly four times too low.

### 3.6 EUI, TEDI and MEUI

The engine reports three intensities, all kWh/m2/yr, so envelope performance can
be judged separately from appliances (as BC Step Code and CHBA do):

```
EUI  = (heating_purch + cooling + hot_water + appliances) / floor_area
TEDI = heating_net / floor_area          (envelope heating demand, before COP)
MEUI = (heating_purch + cooling + hot_water) / floor_area
```

- **TEDI** (Thermal Energy Demand Intensity) isolates the envelope — it is
  independent of the mechanical system, so it is the right basis for the Net Zero
  Ready test. Base plug loads cannot mask a poor envelope, nor sink a good one.
- **MEUI** (Mechanical EUI) is purchased mechanical energy.
- **EUI** is total site energy across all end uses.

The EnerGuide score is a linear approximation of EUI, clamped 0-100
(`100 - (EUI - 30) x 0.8`), for guidance only — not an official rating.

### 3.7 Net Zero Ready probability

The NZR test is run on **TEDI** against a per-zone threshold (30 / 35 / 40 for
zones 6 / 7a / 7b). A single deterministic TEDI hides that real buildings vary —
a home at the threshold is far less safe than one well below it.

The engine runs a **400-run Monte Carlo**: it re-simulates with the uncertain
inputs drawn from normal distributions and reports the fraction of runs whose
TEDI meets the threshold.

| Sampled input | Distribution | Represents |
| --- | --- | --- |
| Weather severity | Normal(1.00, 0.06) | year-to-year weather variation |
| As-built airtightness | Normal(1.00, 0.20) | blower-door scatter vs. target |
| Occupant plug loads | Normal(1.00, 0.20) | occupant behaviour |
| Mechanical COP derate | Normal(0.97, 0.05) | real-world vs. rated efficiency |

Samples are floored at a physical minimum; the run is seeded for stability. For
speed the Monte Carlo runs only on the top ~20 ranked configurations.

```
NZR probability = (runs with TEDI <= threshold) / 400
```

A home with margin scores near 100 percent; one at the threshold near 50. The
test is envelope-based and excludes PV, matching the CHBA definition where Net
Zero *Ready* describes the building itself, not its solar array.

---

## 4. Envelope assemblies, materials and R-values

Sources: `engine/materials.py`, `engine/rvalue.py`, `engine/assemblies.py`

Assembly performance is no longer hand-typed. R-value, cost and embodied carbon
all derive from one material table, so a change to a build-up moves all three
outputs together and consistently.

### 4.1 The material table

Each material carries three per-unit properties (`engine/materials.py`):

```
r_per_in        R-value per inch (imperial)
cost_per_m2_in  installed cost, CAD per m2 per inch of thickness
co2_per_m2_in   embodied carbon, kgCO2e per m2 per inch
```

The full table is listed in section 13. Imperial R converts to metric RSI by
`RSI = R / 5.678`. (A prior version treated imperial R as if it were metric RSI,
making every assembly about 5.7x better insulated than reality — that bug is
fixed here.)

### 4.2 Effective R-value (National Building Code method)

Heat takes two routes through a framed layer: through the insulated cavity and
through the framing members, which bridge the insulation. Following the
National Building Code (A-9.36.2.4, "isothermal planes"), the two routes are
averaged in parallel within the framed layer only, and everything else is
added in series:

```
R_framed_layer = 1 / (ff / R_framing_member + (1 - ff) / R_cavity_insulation)
R_effective    = air_films + continuous_layers + R_framed_layer
U_assembly     = 1 / R_effective
```

- **ff** — framing factor, the fraction of area that is framing (0.23 for 2x6 at
  16" o.c., lower for deep roof joists). Thermal bridging is explicit: the studs
  cut a 2x6 R22 wall well below its nominal R. Adding exterior continuous rigid
  reduces that loss.
- Air films (NRCan): exterior 0.03; interior 0.12 wall / 0.11 ceiling / 0.16
  floor (RSI).
- **Validation:** rebuilt from the engine's material table, two published NBC
  wall worksheets (RSI 3.00 and 3.25) are reproduced within 1%
  (`tests/validation/test_rvalues.py`). Before 2026-10-08 the engine applied
  the parallel path across the whole assembly, which overstated effective R by
  about 5%.

`U_assembly` is what the energy model consumes; `R_nominal` (centre-of-cavity) is
what marketing quotes.

### 4.3 The six assemblies and the thickness sweep

Two walls, two roofs, two floors, each a layer build-up with a swept insulation
thickness (section 13 lists them with computed R ranges). The optimizer searches
the thickness options rather than the user guessing:

- **Walls** — exterior continuous rigid swept 0 / 2 / 4 inches.
- **Roofs** — cavity depth set by the snow-driven joist (section 5); over-deck
  rigid swept 0 / 2 / 4 inches.
- **Floors** — slab-on-grade with sub-slab EPS, or a raised cassette (4.4).

Cost and carbon per m2 come from summing the layers (insulation over the cavity
fraction, framing lumber over its share). Install labour is a fixed hours-per-m2
per assembly type (panelized assemblies install fastest).

### 4.4 Foundation (`engine/foundation.py`)

**Slab on grade.** A 100 mm concrete slab sits on a continuous rigid-EPS
blanket. The blanket covers the footprint and extends **1.5 m beyond all four
sides**. For footprint length `L` and width `W`:

```
footprint_area = L x W
EPS_area       = (L + 3.0) x (W + 3.0)
slab_volume    = footprint_area x 0.100
EPS_volume     = EPS_area x EPS_thickness

U_slab = [1 / (film + concrete + EPS + deep-soil RSI)] x 0.6
```

EPS thickness is swept at 100 / 150 / 200 / 250 mm. For an 8 x 20 m footprint,
the blanket is 11 x 23 m = 253 m2. The 0.6 factor accounts for ground being
warmer than outdoor air over the heating season. The exterior wing's material
quantity, cost and carbon are included; its additional reduction of edge heat
loss is not separately credited in this simplified thermal model.

**Frost wall.** A 300 mm thickened edge runs the perimeter down to the
location's frost depth (section 5). Northern locations with deeper frost lines
pay for more concrete — the location drives foundation cost directly. Reported
quantities include slab concrete, EPS area/volume and frost-wall concrete volume.

**Raised cassette.** The alternative floor is costed *with* the perimeter
grade beam (250 mm, to frost depth) it must sit on, so the two floor systems
compare fairly — neither gets its foundation for free.

If explicit footprint dimensions are unavailable to the Python API, the fallback
is a square plan with the same footprint area. The UI always supplies dimensions.

---

## 5. Location, climate and snow

Sources: `engine/location.py`, `data/ontario_locations.json`

A single location choice (one of 227 Ontario places) resolves four things.

### 5.1 What a location supplies

- **Climate zone** (6 / 7a / 7b) — sets HDD/CDD and the TEDI threshold. Assigned
  by a city-name classifier, user-overridable.
- **Snow load** (Ss, Sr) — real, from the NBCC 2015 workbook.
- **Regional energy rates** — electricity varies by delivery region (section 12).
- **Terrain exposure** — feeds the infiltration wind/shielding correction
  (section 3.2), assigned per delivery region.
- **Soil** — allowable bearing (conservative regional default — soil bearing
  capacity is not climate-driven, and a real value needs a geotechnical
  report per site, not a lookup table) and frost depth (by **climate zone**,
  not delivery region — frost penetration follows winter severity/latitude;
  see section 12 for the sourcing and the correction made to zone 7a).

### 5.2 Roof snow load and joist depth

The ground snow load Ss is converted to a **roof** snow load per NBCC 2015, which
is what actually loads the structure:

```
S = Is x [Ss x (Cb x Cw x Cs x Ca) + Sr]
```

Residential defaults: Is = 1.0 (Normal importance), Cb = 0.8, Cw = Cs = Ca = 1.0,
so `S = 0.8 x Ss + Sr`. The MVP's requested preliminary options are selected
from **ground snow Ss**: Option 1 at `Ss <= 2.5 kPa`, and Option 2 at
`2.5 < Ss <= 3.0 kPa`. Fourteen Ontario locations exceed 3.0 kPa and are placed
in an out-of-range placeholder tier and flagged for structural review.

The placeholder mapping is 10 / 12 / 14 inch joist depth for Option 1 / Option 2
/ out-of-range. Deeper joists hold more insulation, so the selection changes
roof R-value and cost. This is not structural design: span, spacing, dead load,
slope, species/grade, product capacity and deflection still require an engineer.

### 5.3 Municipal context (Pickering pilot)

Sources: `engine/municipal.py`, `data/pickering.json`,
`scripts/import_pickering.py`

The pilot is in Pickering, Ontario, and no parcel has been selected yet. Picking
Pickering (or Pickering (Dunbarton)) attaches a versioned, city-wide snapshot
to the location detail. It does **not** feed any calculation. It is shown as
context only.

- **City inventories** — counts of building footprints, parks,
  neighbourhoods and residential development records, from the City of
  Pickering open-data GIS service. The service's parcel-boundary layer returns
  a single feature, so it is not treated as lot geometry; lot dimensions and
  setbacks remain user assumptions.
- **Multifamily energy benchmark** — Pickering rows of the Ontario 2024
  Energy and Water Reporting and Benchmarking (EWRB) dataset, property type
  "Multifamily Housing", using weather-normalized site EUI (`WN_Site_EUI1`,
  GJ/m2) converted as `kWh/m2 = GJ/m2 / 0.0036`. Nine buildings qualify; the
  median is about 188 kWh/m2/yr (P25 150, P75 272). These are self-reported
  large buildings, so the figure is a local reference point, not a calibration
  or a target for new low-rise homes.
- **Zoning** — not looked up. Zoning status is reported as `not_checked` until a
  parcel is chosen and checked against Pickering's zoning by-laws.

The snapshot is refreshed by running `scripts/import_pickering.py`, which
prints the new JSON for review before `data/pickering.json` is replaced.

---

## 6. Construction cost

Source: `engine/cost.py`

The old flat 1200 CAD/m2 "base cost" — which made two thirds of every estimate
a placeholder — is retired. Every line is now itemized so it can be challenged
and refined individually:

```
subtotal = envelope + connections + partitions + ext_finishes
         + mechanical + fitout
total    = subtotal x (1 + 8% contingency)
```

### 6.1 Envelope (materials + labour)

Each surface area multiplied by its assembly's computed cost per m2 (from the
material layers, section 4), plus windows at catalog rates:

```
materials = opaque_wall_area x wall_cost_m2
          + roof_area        x roof_cost_m2
          + floor_area_surf  x floor_cost_m2   (includes foundation, 4.4)
          + window_area      x window_cost_per_m2

labour_hours = sum(surface_area x install_hours_per_m2)
labour       = labour_hours x 75 CAD/hr (blended crew)
```

Panelized assemblies pay off here: more expensive per m2 of material, roughly
half the installation hours.

### 6.2 Connections

Panel-to-panel joints, sealing tapes, structural fasteners — real cost that a
per-panel material rate misses: **10% of envelope cost**.

### 6.3 Interior partitions

Partition area is taken as **0.9 m2 per m2 of floor** (typical residential
layouts), built as 2x4 studs at 16" o.c. with gypsum both sides, priced from
the same materials table, plus 0.4 hr/m2 install labour.

### 6.4 Exterior finishes

Cladding is already a layer in the wall assemblies. This line covers the rest —
trim, flashings, soffits and fascia — at **15 CAD per m2 of wall**.

### 6.5 Mechanical

The catalog price is a reference for a 150 m2 home; plant capacity scales with
conditioned area, so cost follows a square-root law:

```
mech_cost = catalog_cost x sqrt(floor_area / 150)
```

Two user toggles:

- **Air conditioning** — if the heating plant is a furnace, adds central AC
  (3,000 CAD + 10 CAD/m2). Heat pumps cool inherently at no extra cost.
- **Allow gas** — off means all-electric: gas systems are excluded from the
  search entirely.

### 6.6 Fit-out and services

Kitchens, baths, flooring, paint, plumbing and electrical: **650 CAD/m2**.
This is the honest residue of the old blanket rate — still a lump, but now
explicit, smaller, and challengeable on its own.

### 6.7 Contingency

**8%** on everything above.

### 6.8 Solar

PV is added on top of the construction cost in the optimizer:

```
total_cost = construction_cost + pv_capacity_kw x pv_cost_per_kw
```

### 6.9 Soft costs and soft timeline (Class D)

Source: `engine/soft.py`. Defaults until EnerZen supplies its own allowances.

**Soft costs** = 25% of hard construction cost, covering consultants, permits
and development charges, legal, insurance and financing. This is a common GTA
development pro forma rule of thumb; CMHC treats soft costs as a separate line
from hard costs. Development charges alone vary widely by municipality (CMHC
reports up to 9% of a single-detached home's cost in Toronto), so this
allowance is the first number to replace with real data. Total project cost =
hard cost + soft costs. The budget gate (section 11.2) still compares against
hard cost.

**Soft timeline** (weeks from brief to building permit, assuming complete
applications and no rezoning):

| Phase | Rule | Source |
|-------|------|--------|
| Design and engineering | 8 weeks; 16 for Part 3 buildings or more than 10 units | EnerZen default assumption |
| Site plan approval | 0 for 10 or fewer residential units; otherwise 60 days | Planning Act: Bill 23 exemption; Bill 109 60-day timeline |
| Building permit review | 10 business days for houses, 15 for row houses and other Part 9 buildings, 20 for Part 3 (over 3 storeys or over 600 m2) | Ontario Building Code review periods |

The hard construction timeline is the build schedule in section 7.

---

## 7. Build schedule

Source: `engine/cost.py`

```
fab_weeks     = 1 + total_panels / 30
install_weeks = labour_hours / (4 x 40)
weeks          = fab_weeks + install_weeks
```

A factory setup allowance of one week covers shop drawings, CNC programming and
material staging, followed by production at **30 panels per week** on one line.
A four-person site crew working a forty-hour week gives 160 labour-hours per
week. Labour hours are exactly those from the cost model.

Fabrication and installation are added sequentially as a conservative headline;
in practice, installation may begin once the first panel packages ship. The old
worked comparison to retired catalog assemblies has been removed.

Panel counts assume a standard 2.4 m x 3.0 m panel:

```
panel_area   = 2.4 x 3.0 = 7.2 m2
wall_panels  = round(opaque_wall_area / panel_area)
roof_panels  = round(roof_area / panel_area)
floor_panels = round(floor_area_surf / panel_area)
crane_lifts  = wall_panels + roof_panels + floor_panels
```

**Scope limitation.** This figure is factory fabrication plus site installation
to *envelope close* only. Window and mechanical installation, interior fit-out,
inspections and cure times are excluded, as is any allowance for weather, site
staging, shipping or crane scheduling. Foundation effort is represented through
the selected floor/foundation assembly's install hours, but real excavation and
cure sequencing require a project-specific programme. The result is not a full
construction schedule.

---

## 8. Carbon

Source: `engine/carbon.py`

### 8.1 Embodied carbon

Carbon emitted producing the materials, from EPD-based values in the catalog.

```
embodied = opaque_wall_area x wall_embodied_per_m2
         + roof_area        x roof_embodied_per_m2
         + floor_area_surf  x floor_embodied_per_m2
         + window_area      x window_embodied_per_m2
         + mechanical_embodied
```

PV embodied carbon is added in the optimizer at 1500 kgCO2e per kW installed.

The module also reports a **carbon hotspot** — whichever single component
contributes the most embodied carbon.

### 8.2 Operational carbon

Fuel factors are applied per end use — only heating burns gas in a gas home;
base loads and cooling are always electric:

```
gas home:      operational_annual = heating x 0.19 + everything_else x 0.074
electric home: operational_annual = total_energy x 0.074
operational_30yr = operational_annual x 30      (aligned with lifecycle horizon)
```

- **0.074 kgCO2e/kWh** — Ontario grid intensity, 2024.
- **0.19 kgCO2e/kWh** — natural gas combustion.

Two corrections worth noting: an earlier version applied the gas factor to
*all* energy in gas homes (inflating their operational carbon roughly 2x), and
used a 2022-era grid factor of 0.03 (understating electric systems ~2.5x).
Ontario's grid intensity rose 25 percent in 2024 as gas-fired generation
increased.

---

## 9. Solar

Source: `engine/solar.py`

A specific-yield model. Annual output is the array size multiplied by the yield
per installed kilowatt for the region, derated for orientation.

```
generation = capacity_kw x specific_yield x orientation_derate
cost       = capacity_kw x cost_per_kw
embodied   = capacity_kw x embodied_per_kw
```

| Orientation | Derate |
| --- | --- |
| South | 1.00 |
| East | 0.90 |
| West | 0.90 |
| North | 0.80 |

The orientation derate uses the main facade as a proxy for the available roof
plane, which is an approximation.

### Net energy and net zero

```
net_operational = total_energy - generation
net_EUI         = net_operational / floor_area
net_zero        = net_operational <= 0
```

**Net Zero Ready** and **Net Zero** are different tests. Net Zero Ready concerns
the envelope and is assessed before PV. Net Zero requires generation to meet or
exceed consumption over the year.

---

## 10. Utility bill and lifecycle cost

Source: `engine/finance.py`

### 10.1 Monthly utility bill

Annual demand is distributed across the year using typical Ontario monthly
profiles, then priced. Each profile is normalised so its twelve values sum to 1.

- **Heating** follows the heating degree-day share (peaks in January).
- **Cooling** follows the cooling degree-day share (peaks in July).
- **Base loads** — hot water, appliances, lighting — are spread evenly.
- **PV generation** follows the irradiance share (peaks in summer).

For each month:

```
base_monthly = (total_energy - heating - cooling) / 12
elec_kwh     = cooling_share + base_monthly + (heating if plant is electric)
gas_kwh      = heating_share if plant is gas else 0
net_elec     = elec_kwh - pv_generation_share
elec_cost    = max(net_elec, 0) x electricity_rate
gas_cost     = gas_kwh x gas_rate
monthly_bill = elec_cost + 35 CAD electricity fixed charge
             + (25 CAD gas fixed charge if heating is gas)
```

Net metering is modelled within the month, and the bill floors at zero: surplus
generation offsets consumption but is not paid out or banked across months. The
electricity service charge is always payable; the gas customer charge applies
only to gas-heated configurations. Both defaults come from `energy_rates` and
should be replaced with the applicable utility's current tariff.

### 10.2 Lifecycle cost

The headline is a 30-year present-value calculation, with a 20-year alternate
reported alongside it.

```
upfront = construction_cost + pv_cost - solar_rebate

for each year y in 1..30 (and separately 1..20):
    escalated = annual_energy_cost x (1 + 0.02)^(y-1)
    pv_energy = pv_energy + escalated / (1 + 0.03)^y

lifecycle_total = upfront + pv_energy
```

| Parameter | Value |
| --- | --- |
| Study period | 30 years headline; 20 years alternate |
| Discount rate | 3 percent |
| Energy price escalation | 2 percent per year |

Maintenance, component replacement and residual value are **not** modelled.
Thirty years can still exceed the service life of some mechanical components,
so lifecycle totals should not be read as a full asset-management forecast.

---

## 11. Optimizer and ranking

Source: `engine/optimizer.py`

### 11.1 Airtightness by target

The performance target sets the blower-door target used by the energy model.

| Target | ACH50 |
| --- | --- |
| Code | 5.0 |
| Net Zero Ready | 3.0 |
| Passive House | 1.5 |

### 11.2 Filtering

A configuration is discarded if its total cost (envelope plus PV) exceeds the
budget. Otherwise, if the target is Net Zero Ready or Passive House, a
configuration whose TEDI misses the target's threshold is discarded
(`optimizer.target_performance_passes`; the code target has no TEDI gate).
Only configurations that pass both proceed to ranking.

The gate reports what it did (`optimizer.optimize_with_gate`, returned by
`/optimize` as `gate`): configurations evaluated, passed, rejected over
budget and rejected for missing the target. A configuration over budget is
counted there even if it would also miss the target, so

```
evaluated = passed + over_budget + missed_target
```

When nothing passes, the error names the same breakdown, so the user can see
whether the budget or the target is the binding constraint.

Hard constraints from the brief act before any configuration is built:
mechanical systems the user excluded are never considered, nor gas systems
when the project is all-electric (`optimizer.allowed_mechanical`). The cost
floor used to screen development scenarios applies the same exclusions.

On the development path (`dev_optimizer.excluded_types`), the brief can also
set a minimum bedroom count and a maximum storey count. A catalog type that
fails either never enters a housing mix, and `/dev-scenarios` lists it under
`excluded_types` with the reason. Bedroom counts are per dwelling: Garden
Suite 1, 3-Bedroom Unit 3, Townhouse 3, and MURB 1 (its units are 1- and
2-bedroom per `MURB.pdf`, so 1 is the guaranteed minimum). A custom Path A
brief has no bedroom model, so its bedroom count is not verified.

### 11.3 Pareto ranking

Configuration B **dominates** A when B is at least as good as A on all four
objectives — cost, build time, embodied carbon and EUI — and strictly better on
at least one.

```
rank(A) = 1 + count of configurations that dominate A
```

Rank 1 configurations are non-dominated: nothing else beats them on every axis
simultaneously. They represent the genuine trade-off frontier.

### 11.4 Weighted score

Within a rank, objectives are min-max normalised across all feasible
configurations to a 0-1 scale, then combined using the priority weights. Lower is
better on every objective, so a lower score is better.

```
norm(v) = (v - min) / (max - min)

score = w_cost   x norm(cost)
      + w_speed  x norm(weeks)
      + w_carbon x norm(embodied_carbon)
      + w_energy x norm(EUI)
```

Results are sorted by Pareto rank first, then by weighted score. The top result
is presented as the recommended configuration.

### 11.5 HOT2000 surrogate correction

Source: `engine/surrogate.py`, trained by `scripts/hot2000/train_surrogate.py`
on real HOT2000 v11.13b13 output (`scripts/hot2000/sample_and_run.py` drives
the actual NRCan application via UI automation — see
`scripts/hot2000/HANDOFF.md` for the full pipeline).

Section 3's degree-day model is a closed-form approximation, general across
any floor area, storey count, orientation and climate zone. For one specific
project geometry — Toronto (climate zone 6), ~153 m² floor area, 2-storey,
south-facing, slab-on-grade foundation, gas furnace — a gradient-boosted
model trained on 800 real HOT2000 runs is available instead. Where a project
matches that geometry (floor area within 15 m², matching storeys/
orientation/climate zone, `FA1` slab foundation, gas heating), the optimizer
replaces the approximation's `eui_kwh_m2_yr` and `tedi_kwh_m2_yr` with the
surrogate's prediction, recomputes NZR compliance and EnerGuide score from
the corrected TEDI/EUI, and populates `peak_heating_load_w` (not otherwise
available from the degree-day model). Held-out validation against the
training run: R²=0.979 (EUI), 0.989 (TEDI), 0.989 (peak heating load);
re-verifying the surrogate's top-20 ranked configurations against fresh real
HOT2000 runs matched within 0.2-0.4 kWh/m²/yr on EUI.

Every other project geometry — which is to say, almost every real project —
falls back to the section 3 model unchanged. Extending surrogate coverage to
other geometries means training on additional HOT2000 base house files
(different storeys/orientation/foundation/fuel combinations), not something
this pass attempted.

---

## 12. Reference data

{{CLIMATE_TABLE}}

{{RATES_TABLE}}

{{REGIONS_TABLE}}

{{SNOW_TABLE}}

{{BENCHMARK_TABLE}}

---

## 13. Assembly catalog

{{CATALOG_TABLES}}

---

## 14. Site planning

Source: `engine/site.py`

Given a building footprint (already fixed by the optimizer above) and a lot,
this module computes where the building and driveway sit on the lot, and how
well the fixed orientation captures passive solar gain. It does not choose or
change the building's orientation — that is a `ProjectSpec` input that already
drove the energy simulation (section 3), so re-optimizing it here would
invalidate the energy results upstream. What it optimizes is placement within
the buildable envelope.

### Inputs

A `SiteSpec`: lot width (east-west) and depth (north-south) in metres, which
lot edge fronts the street, and front/side/rear setbacks in metres (defaults
6.0 / 1.2 / 7.5 m, typical suburban Ontario zoning figures — confirm against
the actual municipal bylaw before relying on them).

### Buildable envelope

The lot minus setbacks. The setback that applies to each edge depends on
which edge fronts the street:

```
street on N or S:  x-envelope = [side_setback, lot_width - side_setback]
                    y-envelope = front/rear setback from whichever edge is the street
street on E or W:  axes swap
```

### Passive-solar placement

Per NREL/DOE passive-solar guidance and the LEED orientation credit, main
glazing facing true south captures the most winter solar gain, with a
majority of the benefit retained within about 30 degrees of south. The
footprint's longer dimension is placed along the facade that faces the
project's fixed orientation, since a longer solar-facing wall carries more
glazing area:

```
orientation in {N, S}: east-west extent = long dimension, north-south extent = short dimension
orientation in {E, W}: axes swap
```

The building is then centered in the buildable envelope. If the footprint
does not fit the envelope at that orientation, the layout is still returned
(centered, allowed to overflow) with `fits_on_lot = False` and a note — this
surfaces the conflict rather than silently relocating or resizing the
building.

**Solar score** (0 to 1, informational, not a pass/fail gate): a cosine
falloff from true south —

```
solar_score = 0.5 + 0.5 x cos(angular_distance_from_south)
```

giving 1.00 at due south, ~0.93 at 30 degrees off south, 0.50 at due east/west,
and 0.00 at due north. This is the same relationship the cited guidance
describes qualitatively, expressed as a continuous score instead of a
threshold.

### Driveway

Sited as a 3 m-wide strip from the street edge to the building, offset to one
side of the buildable envelope so it does not sit in front of the
solar-facing facade.

### Output

A `SiteLayout` (building position/size, driveway polygon, orientation, solar
score, `fits_on_lot`/`setbacks_ok` flags) and a hand-built SVG diagram (lot
boundary, dashed setback line, building footprint with its solar-facing edge
highlighted, driveway, north-up orientation label) — the technical,
to-scale reference. An optional AI-generated concept illustration
(`engine/ai.py`, OpenAI image generation) may accompany it for visual
presentation, but is explicitly illustrative only: text-to-image models
cannot hold exact setback distances or right angles, so the SVG — not the
illustration — is the source of truth for any dimension.

### Building archetypes

Source: `engine/archetypes.py`. The development path places these catalog
types, sized from EnerZen's drawings:

| Type | Storeys | Footprint (E-W x N-S) | Units | Area per unit | Basis |
|------|---------|-----------------------|-------|---------------|-------|
| Garden Suite (1 BR) | 1 | 7.0 x 6.5 m | 1 | 46 m2 | Garden Suite drawing I121 (366 ft2 net interior) |
| 3-Bedroom Unit | 2 | 10.0 x 8.0 m | 1 | 163 m2 | 3 BHK unit DWG (1,750 ft2) |
| MURB | 5 | 19.0 x 18.0 m | 20 | 65 m2 | MURB.pdf and the G+4 DWG: ground + 4 floors, 4 units per floor, 695 ft2 two-bed units |
| Townhouse (3 BR, attached) | 2 | 6.0 x 12.0 m per unit | 1 per unit | 150 m2 | Catalog placeholder |

The MURB footprint is scaled from the PDF plans (about 19.3 x 18 m) because
the dimension strings are on the DWG; confirm against the DWG.

### Development path stages

Source: `engine/dev_optimizer.py`. Path B follows the developer flowchart:

1. **Scenarios (typology engine + 2D site plan).** Mixes of the allowed types
   are enumerated, capped by buildable area and budget. A mix is kept when it
   fits inside the setbacks and its *cost floor* is within budget. The floor
   is the cheapest catalog configuration of each type, costed without the
   energy simulation (`optimizer.baseline_cost`), so no mix the optimizer
   could make affordable is dropped. Scenarios are ordered by the yield and
   cost priorities.
   Types that fail the brief's minimum bedrooms or maximum storeys never enter
   a mix and are listed with the reason (section 11.2).
2. **User review.** The user reviews the site plans, may revise the brief up to
   three times, and approves the scenarios to carry forward.
3. **Building performance optimization and development calculations.** Each
   approved housing type is optimized once (section 11); a scenario's totals
   scale by its dwelling count. Scenarios whose optimized hard cost exceeds
   the budget, or whose types have no configuration meeting the target, are
   set aside with the reason. The rest are ranked by the yield, cost, energy
   and carbon weights.

Dwellings: a MURB counts all of its units (`units_per_building`) for yield,
cost, floor area, utility and Net Zero Ready totals. Development
calculations per scenario: hard cost, soft costs and total project cost
(section 6.9), the soft timeline for the largest building and the total
dwelling count, fabrication-to-close weeks summed across homes (the factory
produces them in sequence), floor-area-weighted EUI, embodied and 30-year
lifecycle carbon, and the 30-year lifecycle cost.

### Development site plan

Sources: `engine/multi_site.py`, `engine/site_geometry.py`

For a housing mix, buildings are placed in two bands either side of a shared
walkway when they fit, otherwise in rows across the buildable envelope. The
concept layers are then drawn from one metre-based geometry model:

- **Walkway** — 1.8 m wide, from the street to the rear garden. It runs down
  the lot centre when that is clear; otherwise through the clear corridor
  between buildings (at least 1.8 m plus 0.4 m clearance each side) nearest
  the centre. If no corridor exists, only an entry walk to the setback line is
  drawn and the plan says so.
- **Entrances** — front doors face the street, as on the EnerZen Garden Suite
  and MURB drawings. A door moves to the side facing the walkway when its
  street face would open onto a parking stall, or when the street face is the
  short end of a townhouse row (each townhouse then gets its own door along
  that long face). A 1.2 m path joins each porch to the walkway when it can do
  so without crossing a building or stall.
- **Building detail** — MURBs show the corridor, elevator core and balconies
  from the unit drawings; townhouse rows show party walls between units.
- **Parking** — 2.7 x 5.5 m placeholder stalls in the front setback, either
  side of the walkway, only when the frontage holds one per unit.
- **Shared green** — the rear setback becomes one shared garden strip (inset
  0.75 m) when it is at least 2.5 m deep, otherwise a small amenity corner.
  Trees are spaced roughly every 5 m along it, with a rain-garden marker at
  one end.

These are planning concepts, not a landscape design or site plan approval.

---

## 15. Feasibility report

Sources: `engine/feasibility.py` (assessment), `engine/report.py` (layout),
`/report` (Path A) and `/dev-report` (Path B).

### 15.1 Status

The status comes from a list of checks, each pass, fail or not checked:

| Status | Rule |
| --- | --- |
| FEASIBLE | Every check passes and no constraint was relaxed |
| FEASIBLE WITH MODIFICATIONS | Every check passes, but only after a named constraint was relaxed |
| FURTHER STUDY REQUIRED | Any check failed or was not made |

The checks are the budget and performance gate (section 11.2), the brief's
hard constraints, site fit, and zoning. **Zoning is always "not checked"**:
no Pickering parcel is selected and no municipal rules are evaluated, so
every report currently reads FURTHER STUDY REQUIRED and says why, rather
than claiming feasibility. On Path A, a site-fit failure no longer refuses
the report; it is a failed check. Without a lot, site fit is not checked.
The engine does not yet relax constraints on its own, so FEASIBLE WITH
MODIFICATIONS is defined but not produced until a relaxation step exists.

On Path B the report covers one approved mix (the top-ranked by default).
All approved mixes are re-evaluated so it can be ranked against them; the
gate check counts how many passed.

### 15.2 Sections

1. **Executive feasibility** — status, reasons, the checks, and headline
   numbers.
2. **Recommended solution** — Path A: design basis and selected systems with
   effective R-values and foundation quantities. Path B: the mix and each
   type's systems, a to-scale plan (lot, buildings, shared green, rain-garden
   marker, walkway, parking) drawn from the placement engine, and the
   green-space strategy: shared green area and share of the lot, and site
   coverage. No 3D.
3. **Capital cost (Class D)** — hard cost, soft costs (section 6.9), total
   and budget.
4. **Timeline** — soft timeline (section 6.9), fabrication and site work to
   envelope close (section 7), and the sum.
5. **Energy** — EUI, TEDI against the target's threshold, MEUI, PV and net
   energy; Path B per type and area-weighted.
6. **Carbon** — embodied, 30-year operational and lifecycle totals in tCO2e
   first, then per m2, with the new low-rise embodied benchmark.
7. **Lifecycle economics** — against a code-built new home of the same area
   (15.3).
8. **Priority achievement** — for each weighted objective, the
   recommendation's rank among every feasible option (rank 1 is best; ties
   share the better rank). Path A: cost, speed, embodied carbon and EUI
   across all configurations that passed the gate. Path B: yield, cost, EUI
   and embodied carbon across the feasible approved mixes.
9. **Next steps** — required items driven by what was not checked
   (zoning → municipal pre-consultation; site fit; regional soil defaults →
   geotechnical investigation; preliminary snow-to-joist mapping →
   structural engineer; a screening energy model → compliance model; Part 3
   buildings; more than 10 dwellings → site plan application; catalog
   defaults → EnerZen procurement data), then enhancements listed
   separately.

### 15.3 Code-built benchmark

From `data/assemblies.json` → `benchmarks`: capital cost $2,200/m2
(conventional new build), site EUI 130 kWh/m2/yr (code-built new) and
embodied carbon 184 kgCO2e/m2.

```
benchmark capital   = 2,200 x floor area
benchmark energy    = 130 x floor area                       (kWh/yr)
variable rate       = (annual utility - fixed charges) / (gross energy - PV)
benchmark utility   = fixed charges + benchmark energy x variable rate
energy saving       = benchmark energy - (gross energy - PV)
lifecycle saving    = LCC(benchmark capital, benchmark utility) - LCC(recommended)
```

Pricing the benchmark at the recommendation's own variable rate isolates
consumption from fuel choice. Fixed charges are the electricity service
charge, plus the gas customer charge when the recommendation burns gas. LCC
is section 10.2 over 30 years. Path B sums each type's comparison over its
dwellings.

