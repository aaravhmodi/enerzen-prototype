"""
HOT2000-inspired energy simulation model.

This is a simplified degree-day based model that approximates HOT2000 outputs
for EnerZen's standard assembly combinations. When HOT2000 is integrated, this
module gets replaced with a wrapper around the actual software — the interface
stays the same.
"""

import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class BuildingSpec:
    floor_area_m2: float
    storeys: int
    climate_zone: str
    orientation: str  # N, S, E, W (main facade)
    window_to_wall_ratio: float  # 0.0 - 0.5
    infiltration_ach50: float  # blower door target


@dataclass
class AssemblyConfig:
    wall_u: float       # W/m²K
    roof_u: float
    floor_u: float
    window_u: float     # W/m²K
    window_shgc: float
    mechanical_cop: float
    mechanical_type: str  # "gas" or "electric"
    hrv_efficiency: float = 0.0


@dataclass
class EnergyResult:
    eui_kwh_m2_yr: float          # Energy Use Intensity
    heating_demand_kwh_yr: float
    cooling_demand_kwh_yr: float
    hot_water_kwh_yr: float
    total_energy_kwh_yr: float
    energuide_score: float         # approximate
    nzr_compliant: bool
    nzr_threshold: float


# Climate data from assemblies.json (HDD/CDD for degree-day model).
# heating_season_days bounds the period over which internal/solar gains are
# credited against heating demand.
CLIMATE = {
    "6":  {"hdd": 3520, "cdd": 320,  "nzr_eui": 60, "design_heat": -18,
           "heating_season_days": 230},
    "7a": {"hdd": 4440, "cdd": 220,  "nzr_eui": 55, "design_heat": -25,
           "heating_season_days": 250},
    "7b": {"hdd": 5500, "cdd": 130,  "nzr_eui": 50, "design_heat": -30,
           "heating_season_days": 270},
}

# ── Internal + solar gains ───────────────────────────────────────────────────
# Heat generated inside the building offsets heating demand. The old model
# ignored this entirely and used a crude `solar_factor` multiplier instead,
# which over-predicted heating badly (a code home computed at 83% heating vs
# NRCan's 61% actual share of residential energy).

OCCUPANT_SENSIBLE_W = 100    # sensible heat per person, ASHRAE residential
OCCUPANT_PRESENCE   = 0.60   # fraction of hours occupied
APPLIANCE_TO_HEAT   = 0.90   # fraction of appliance/lighting energy ending as heat
DHW_TO_HEAT         = 0.20   # tank + pipe losses released indoors
GAIN_UTILISATION    = 0.90   # useful fraction in a cold-climate heating season

# Solar irradiance on a vertical surface over the heating season (kWh/m2),
# southern Ontario. Drives passive gain through glazing.
VERTICAL_IRRADIANCE = {"S": 450, "E": 260, "W": 260, "N": 160}

# Glazing distribution: fraction of window area on the main facade vs. the rest.
GLAZING_DISTRIBUTION = {"main": 0.40, "opposite": 0.20, "side": 0.20}
_OPPOSITE = {"S": "N", "N": "S", "E": "W", "W": "E"}
_SIDES = {"S": ("E", "W"), "N": ("E", "W"), "E": ("N", "S"), "W": ("N", "S")}

WINDOW_FRAME_FACTOR = 0.70   # glazed fraction of rough opening
SHADING_FACTOR      = 0.85   # overhangs, neighbours, dirt


def occupants_for(floor_area_m2: float) -> float:
    """
    Derived occupancy. Canadian average household is ~2.4 people; this scales
    with floor area so a 150 m2 home lands near 3.0.
    """
    return max(1.0, 1.0 + floor_area_m2 / 75)


def solar_gain_kwh(window_area_m2: float, shgc: float, orientation: str) -> float:
    """Passive solar gain through glazing over the heating season."""
    dist = {
        orientation: GLAZING_DISTRIBUTION["main"],
        _OPPOSITE.get(orientation, "N"): GLAZING_DISTRIBUTION["opposite"],
    }
    for s in _SIDES.get(orientation, ("E", "W")):
        dist[s] = dist.get(s, 0) + GLAZING_DISTRIBUTION["side"]

    total = 0.0
    for facing, frac in dist.items():
        total += (window_area_m2 * frac * WINDOW_FRAME_FACTOR * shgc
                  * VERTICAL_IRRADIANCE.get(facing, 260) * SHADING_FACTOR)
    return total

# Envelope surface area ratios relative to floor area (typical residential forms)
SURFACE_RATIOS = {
    1: {"wall": 1.8, "roof": 1.05, "floor": 1.0},   # single storey
    2: {"wall": 1.4, "roof": 0.55, "floor": 0.52},  # two storey
    3: {"wall": 1.2, "roof": 0.40, "floor": 0.38},  # three storey
}


def simulate(spec: BuildingSpec, config: AssemblyConfig,
             weather_factor: float = 1.0, infiltration_factor: float = 1.0,
             plug_factor: float = 1.0, cop_factor: float = 1.0) -> EnergyResult:
    """
    The *_factor arguments perturb uncertain real-world inputs and default to
    1.0 (deterministic). They are used by nzr_probability() for Monte Carlo:
      weather_factor      — weather-year severity (scales degree days)
      infiltration_factor — as-built airtightness vs. target
      plug_factor         — occupant plug/appliance loads
      cop_factor          — real-world mechanical efficiency derate
    """
    climate = CLIMATE[spec.climate_zone]
    hdd = climate["hdd"] * weather_factor
    cdd = climate["cdd"] * weather_factor
    nzr_threshold = climate["nzr_eui"]

    ratios = SURFACE_RATIOS.get(spec.storeys, SURFACE_RATIOS[2])
    wall_area = spec.floor_area_m2 * ratios["wall"]
    roof_area = spec.floor_area_m2 * ratios["roof"]
    floor_area = spec.floor_area_m2 * ratios["floor"]
    window_area = wall_area * spec.window_to_wall_ratio
    opaque_wall_area = wall_area - window_area

    # Transmission losses (W/K)
    ua_wall    = opaque_wall_area * config.wall_u
    ua_roof    = roof_area        * config.roof_u
    ua_floor   = floor_area       * config.floor_u
    ua_windows = window_area      * config.window_u

    # Infiltration losses — convert ACH50 to natural infiltration (÷ 20 rule of thumb)
    ach_natural = spec.infiltration_ach50 * infiltration_factor / 20
    volume_m3 = spec.floor_area_m2 * 2.7 * spec.storeys
    ua_infiltration = (ach_natural * volume_m3 * 0.33)  # W/K, 0.33 = air heat capacity factor

    # HRV recovery reduces ventilation load
    hrv_factor = 1 - config.hrv_efficiency
    ua_vent = ua_infiltration * hrv_factor

    ua_total = ua_wall + ua_roof + ua_floor + ua_windows + ua_vent

    # ── Base loads ──────────────────────────────────────────────────────────
    # Scaled to occupancy and floor area, calibrated against NRCan shares
    # (space heating 61%, water heating ~18%, appliances/lighting ~21% of
    # Canadian residential energy). Hot water previously divided by storeys,
    # which had no physical basis and ran ~4x low.
    occupants = occupants_for(spec.floor_area_m2)
    hot_water = occupants * 1800                                # kWh/yr
    appliances = (1500 + 20 * spec.floor_area_m2) * plug_factor  # kWh/yr

    # ── Heating: gross loss less useful gains ───────────────────────────────
    season_days = climate["heating_season_days"]
    season_frac = season_days / 365
    season_hours = season_days * 24

    gross_loss = ua_total * hdd * 24 / 1000                     # kWh/yr

    gain_internal = (appliances * APPLIANCE_TO_HEAT * season_frac
                     + hot_water * DHW_TO_HEAT * season_frac
                     + occupants * OCCUPANT_SENSIBLE_W * OCCUPANT_PRESENCE
                       * season_hours / 1000)
    gain_solar = solar_gain_kwh(window_area, config.window_shgc, spec.orientation)

    useful_gains = GAIN_UTILISATION * (gain_internal + gain_solar)
    heating_net = max(0.0, gross_loss - useful_gains)
    heating_demand = heating_net / (config.mechanical_cop * cop_factor)

    # Cooling demand (simplified — smaller fraction for Canadian climate)
    cooling_demand = (ua_windows * config.window_shgc * cdd * 24 / 1000) * 0.4
    cooling_demand /= 3.5  # typical cooling COP

    total_energy = heating_demand + cooling_demand + hot_water + appliances
    eui = total_energy / spec.floor_area_m2

    # EnerGuide score approximation (inverse of EUI, scaled to ~100 for NZR homes)
    energuide_score = max(0, min(100, 100 - (eui - 30) * 0.8))

    return EnergyResult(
        eui_kwh_m2_yr=round(eui, 1),
        heating_demand_kwh_yr=round(heating_demand, 0),
        cooling_demand_kwh_yr=round(cooling_demand, 0),
        hot_water_kwh_yr=round(hot_water, 0),
        total_energy_kwh_yr=round(total_energy, 0),
        energuide_score=round(energuide_score, 1),
        nzr_compliant=eui <= nzr_threshold,
        nzr_threshold=nzr_threshold,
    )


def nzr_probability(spec: BuildingSpec, config: AssemblyConfig,
                    pv_offset_eui: float = 0.0, n: int = 400, seed: int = 42) -> float:
    """
    Probability the home meets its Net Zero Ready EUI threshold once real-world
    variance is accounted for. Monte Carlo: sample the uncertain inputs, run the
    model, and return the fraction of runs at or below threshold.

    pv_offset_eui: EUI offset from on-site PV (kWh/m²/yr) subtracted from each
    sampled result — lets solar improve the odds.

    Distributions reflect typical as-built construction variance:
      weather-year severity   ~ Normal(1.00, 0.06)
      as-built airtightness   ~ Normal(1.00, 0.20), floored (tighter is better,
                                but blower-door results scatter above target)
      occupant plug loads     ~ Normal(1.00, 0.20)
      mechanical COP derate   ~ Normal(0.97, 0.05)
    """
    rng = random.Random(seed)
    threshold = CLIMATE[spec.climate_zone]["nzr_eui"]
    hits = 0
    for _ in range(n):
        weather = max(0.7, rng.gauss(1.00, 0.06))
        infil   = max(0.5, rng.gauss(1.00, 0.20))
        plug    = max(0.4, rng.gauss(1.00, 0.20))
        cop     = max(0.6, rng.gauss(0.97, 0.05))
        r = simulate(spec, config, weather_factor=weather, infiltration_factor=infil,
                     plug_factor=plug, cop_factor=cop)
        if r.eui_kwh_m2_yr - pv_offset_eui <= threshold:
            hits += 1
    return round(hits / n, 3)
