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
(a code 2x6 R22 wall computes to ~R16 effective, matching published values). But
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

Areas are derived from floor area using fixed ratios per storey count. These are
generic residential forms, not EnerZen's actual designed units.

| Storeys | Wall ratio | Roof ratio | Floor ratio |
| --- | --- | --- | --- |
| 1 | 1.80 | 1.05 | 1.00 |
| 2 | 1.40 | 0.55 | 0.52 |
| 3 | 1.20 | 0.40 | 0.38 |

```
wall_area        = floor_area x wall_ratio
roof_area        = floor_area x roof_ratio
floor_area_surf  = floor_area x floor_ratio
window_area      = wall_area x window_to_wall_ratio
opaque_wall_area = wall_area - window_area
```

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
the test condition; the model uses the standard **divide-by-20 rule of thumb**:

```
ACH_natural     = ACH50 / 20
volume          = total_conditioned_floor_area x 2.7
UA_infiltration = ACH_natural x volume x 0.33
```

- `2.7` is the assumed storey height in metres.
- `0.33` is the volumetric heat capacity of air in Wh/(m3.K).

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

### 4.2 Effective R-value (parallel-path)

Heat takes two routes through a framed assembly: through the insulated cavity and
through the framing members, which bridge the insulation. Each path's resistance
is summed, converted to a U-factor, and area-weighted by the framing fraction:

```
R_cavity_path  = air_films + continuous_layers + cavity_insulation
R_framing_path = air_films + continuous_layers + framing_member
U_assembly     = ff x (1 / R_framing_path) + (1 - ff) x (1 / R_cavity_path)
R_effective    = 1 / U_assembly
```

- **ff** — framing factor, the fraction of area that is framing (0.23 for 2x6 at
  16" o.c., lower for deep roof joists). This finally makes thermal bridging
  explicit: a code 2x6 R22 wall loses ~25% of its nominal R to the studs, landing
  at ~R16 effective. Adding exterior continuous rigid cuts that loss.
- Air films (NRCan): exterior 0.03; interior 0.12 wall / 0.11 ceiling / 0.16
  floor (RSI).

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
- **Soil** — allowable bearing and frost depth, conservative regional defaults.

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
budget. If the target is Net Zero Ready, configurations whose deterministic EUI
misses the threshold are also discarded.

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
