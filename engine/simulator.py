"""
HOT2000-inspired energy simulation model.

This is a simplified degree-day based model that approximates HOT2000 outputs
for EnerZen's standard assembly combinations. When HOT2000 is integrated, this
module gets replaced with a wrapper around the actual software — the interface
stays the same.
"""

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


# Climate data from assemblies.json (HDD/CDD for degree-day model)
CLIMATE = {
    "6":  {"hdd": 3520, "cdd": 320,  "nzr_eui": 60, "design_heat": -18},
    "7a": {"hdd": 4440, "cdd": 220,  "nzr_eui": 55, "design_heat": -25},
    "7b": {"hdd": 5500, "cdd": 130,  "nzr_eui": 50, "design_heat": -30},
}

# Envelope surface area ratios relative to floor area (typical residential forms)
SURFACE_RATIOS = {
    1: {"wall": 1.8, "roof": 1.05, "floor": 1.0},   # single storey
    2: {"wall": 1.4, "roof": 0.55, "floor": 0.52},  # two storey
    3: {"wall": 1.2, "roof": 0.40, "floor": 0.38},  # three storey
}


def simulate(spec: BuildingSpec, config: AssemblyConfig) -> EnergyResult:
    climate = CLIMATE[spec.climate_zone]
    hdd = climate["hdd"]
    cdd = climate["cdd"]
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
    ach_natural = spec.infiltration_ach50 / 20
    volume_m3 = spec.floor_area_m2 * 2.7 * spec.storeys
    ua_infiltration = (ach_natural * volume_m3 * 0.33)  # W/K, 0.33 = air heat capacity factor

    # HRV recovery reduces ventilation load
    hrv_factor = 1 - config.hrv_efficiency
    ua_vent = ua_infiltration * hrv_factor

    ua_total = ua_wall + ua_roof + ua_floor + ua_windows + ua_vent

    # Degree-day heating demand (kWh/yr)
    # Solar gains reduce heating demand — south-facing captures more
    solar_factor = {"S": 0.82, "N": 0.95, "E": 0.90, "W": 0.90}.get(spec.orientation, 0.90)
    heating_demand = (ua_total * hdd * 24 / 1000) * solar_factor
    heating_demand /= config.mechanical_cop

    # Cooling demand (simplified — smaller fraction for Canadian climate)
    cooling_demand = (ua_windows * config.window_shgc * cdd * 24 / 1000) * 0.4
    cooling_demand /= 3.5  # typical cooling COP

    # Hot water (CMHC average for residential)
    hot_water = 15 * spec.floor_area_m2 / spec.storeys  # kWh/yr, scales with units

    # Appliances and lighting (fixed, not assembly-dependent)
    appliances = 25 * spec.floor_area_m2  # kWh/yr

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
