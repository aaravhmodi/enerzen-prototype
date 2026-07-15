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
tool. Reported EUIs run optimistic relative to published benchmarks; part of that
gap is genuine performance and part is model simplification.

**Geometry is generic.** Surface areas come from floor-area ratios for typical
residential forms, not from EnerZen's actual designed units. Storey height is
assumed at 2.7 m for the volume calculation, while wall area comes from the
ratios — so height is effectively assumed twice, by two unlinked routes.

**Cost is dominated by a placeholder.** The 1200 CAD/m2 base cost is roughly two
thirds of the reported total and is not modelled. Window and mechanical
installation labour is omitted entirely.

**Build time covers envelope close only.** It is not a project schedule.

**Cooling is glazing-driven only**, and uses a hard-coded COP of 3.5 rather than
the selected mechanical system's rating.

**Lifecycle cost omits maintenance and replacement**, which will understate the
true cost of any system over 60 years.

**Benchmarks and rates are provincial averages** drawn from secondary sources.
They are adequate for directional comparison in a prototype and should be
replaced with EnerZen's own project data before any number is quoted to a client.

**The Monte Carlo distributions are engineering judgement.** They are plausible
representations of as-built variance but are not calibrated against measured
EnerZen blower-door or energy-bill data. The probability is therefore a
structured estimate of confidence, not a validated statistic.

---

## 2. What the engine does

The engine takes a project description and searches for the best assembly
configuration. It is a deterministic physics-and-costing model — there is no
machine learning anywhere in it.

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
      |-- finance.py   : monthly utility bill, 60-year lifecycle cost
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
volume          = floor_area x 2.7 x storeys
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

## 4. Construction cost

Source: `engine/cost.py`

```
total = materials + labour + base_cost
```

### 4.1 Materials

Each surface area multiplied by its catalog unit rate, plus the flat mechanical
system cost.

```
materials = opaque_wall_area x wall_cost_per_m2
          + roof_area        x roof_cost_per_m2
          + floor_area_surf  x floor_cost_per_m2
          + window_area      x window_cost_per_m2
          + mechanical_cost
```

### 4.2 Labour

Only wall, roof and floor installation hours are counted. Window and mechanical
installation labour is **not** modelled.

```
labour_hours = opaque_wall_area x wall_install_hours_per_m2
             + roof_area        x roof_install_hours_per_m2
             + floor_area_surf  x floor_install_hours_per_m2

labour = labour_hours x 75
```

The blended crew rate is **75 CAD/hour**. This is where panelized assemblies pay
off: they cost more per square metre in materials but need roughly half the
installation hours.

### 4.3 Base cost

```
base_cost = floor_area x 1200
```

A flat **1200 CAD/m2** covering everything outside the envelope model:
foundation, structural framing, interior finishes, plumbing, electrical.

It is deliberately held constant across configurations so that comparing two
assemblies only moves the parts that genuinely differ. The consequence is that
roughly two thirds of the reported cost is a placeholder rather than a modelled
quantity, and assembly choice only swings the remaining third.

### 4.4 Solar

PV is added on top of the construction cost in the optimizer:

```
total_cost = construction_cost + pv_capacity_kw x pv_cost_per_kw
```

### 4.5 Worked example

A 150 m2, two-storey home, 20 percent window-to-wall, with wall W4, roof R2,
floor F2, windows GL2 and mechanical M3.

```
wall_area        = 150 x 1.40 = 210.0 m2
window_area      = 210 x 0.20 =  42.0 m2
opaque_wall_area = 210 -  42  = 168.0 m2
roof_area        = 150 x 0.55 =  82.5 m2
floor_area_surf  = 150 x 0.52 =  78.0 m2
```

| Component | Quantity | Rate | Cost |
| --- | --- | --- | --- |
| Opaque wall (W4) | 168.0 m2 | 155 /m2 | 26,040 |
| Roof (R2) | 82.5 m2 | 110 /m2 | 9,075 |
| Floor (F2) | 78.0 m2 | 95 /m2 | 7,410 |
| Windows (GL2) | 42.0 m2 | 680 /m2 | 28,560 |
| Mechanical (M3) | 1 | 20,000 | 20,000 |
| Materials subtotal | | | 91,085 |
| Labour | 135.9 hr | 75 /hr | 10,193 |
| Base cost | 150 m2 | 1,200 /m2 | 180,000 |
| **Total** | | | **281,278** |

---

## 5. Build schedule

Source: `engine/cost.py`

```
weeks = labour_hours / (4 x 40)
```

A four-person crew working a forty-hour week gives 160 labour-hours per week.
Labour hours are exactly those from the cost model.

Using the worked example above, 135.9 hours gives roughly 0.85 weeks. The same
home in stick-frame assemblies (W1/R1/F1) needs about 312.6 hours, or roughly
2.0 weeks — about 2.3 times slower.

Panel counts assume a standard 2.4 m x 3.0 m panel:

```
panel_area   = 2.4 x 3.0 = 7.2 m2
wall_panels  = round(opaque_wall_area / panel_area)
roof_panels  = round(roof_area / panel_area)
floor_panels = round(floor_area_surf / panel_area)
crane_lifts  = wall_panels + roof_panels + floor_panels
```

**Scope limitation.** This figure is time to *envelope close* only. Foundation,
window and mechanical installation, interior fit-out, inspections and cure times
are excluded, as is any allowance for weather, staging or crane scheduling. It is
not a project programme.

---

## 6. Carbon

Source: `engine/carbon.py`

### 6.1 Embodied carbon

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

### 6.2 Operational carbon

```
grid_factor        = 0.19 if mechanical is gas else 0.074
operational_annual = total_energy x grid_factor
operational_60yr   = operational_annual x 60
```

- **0.074 kgCO2e/kWh** — Ontario grid intensity, 2024.
- **0.19 kgCO2e/kWh** — natural gas combustion.

Note that Ontario's grid intensity rose 25 percent in 2024 as gas-fired
generation increased. An earlier version of this engine used 0.03, a 2022-era
figure, which understated the operational carbon of electric systems by roughly
two and a half times.

---

## 7. Solar

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

## 8. Utility bill and lifecycle cost

Source: `engine/finance.py`

### 8.1 Monthly utility bill

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
```

Net metering is modelled within the month, and the bill floors at zero: surplus
generation offsets consumption but is not paid out or banked across months.

### 8.2 Lifecycle cost

A 60-year present-value calculation.

```
upfront = construction_cost + pv_cost - solar_rebate

for each year y in 1..60:
    escalated = annual_energy_cost x (1 + 0.02)^(y-1)
    pv_energy = pv_energy + escalated / (1 + 0.03)^y

lifecycle_total = upfront + pv_energy
```

| Parameter | Value |
| --- | --- |
| Study period | 60 years |
| Discount rate | 3 percent |
| Energy price escalation | 2 percent per year |

Maintenance, component replacement (a heat pump will not last 60 years) and
residual value are **not** modelled.

---

## 9. Optimizer and ranking

Source: `engine/optimizer.py`

### 9.1 Airtightness by target

The performance target sets the blower-door target used by the energy model.

| Target | ACH50 |
| --- | --- |
| Code | 5.0 |
| Net Zero Ready | 3.0 |
| Passive House | 1.5 |

### 9.2 Filtering

A configuration is discarded if its total cost (envelope plus PV) exceeds the
budget. If the target is Net Zero Ready, configurations whose deterministic EUI
misses the threshold are also discarded.

### 9.3 Pareto ranking

Configuration B **dominates** A when B is at least as good as A on all four
objectives — cost, build time, embodied carbon and EUI — and strictly better on
at least one.

```
rank(A) = 1 + count of configurations that dominate A
```

Rank 1 configurations are non-dominated: nothing else beats them on every axis
simultaneously. They represent the genuine trade-off frontier.

### 9.4 Weighted score

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

## 10. Reference data

{{CLIMATE_TABLE}}

{{RATES_TABLE}}

{{BENCHMARK_TABLE}}

---

## 11. Assembly catalog

{{CATALOG_TABLES}}
