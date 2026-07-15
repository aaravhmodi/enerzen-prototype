"""
Location resolution: a place name -> the parameters the rest of the engine needs.

A single location choice drives four things:
  - snow load  : roof snow load S (NBCC 2015) -> structural snow tier / joist depth
  - climate    : climate zone (HDD/CDD, TEDI threshold) for the energy model
  - rates      : regional electricity/gas prices for utility + lifecycle cost
  - soil       : allowable bearing + frost depth for foundation sizing

Location snow/zone/region come from data/ontario_locations.json (built from the
NBCC workbook by scripts/build_locations.py). Rates/soil/snow-tier definitions
come from data/assemblies.json.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


@lru_cache(maxsize=1)
def _locations() -> dict:
    with open(DATA_DIR / "ontario_locations.json", encoding="utf-8") as f:
        return json.load(f)["locations"]


@lru_cache(maxsize=1)
def _catalog() -> dict:
    with open(DATA_DIR / "assemblies.json", encoding="utf-8") as f:
        return json.load(f)


def location_names() -> list[str]:
    return list(_locations().keys())


def roof_snow_load(ss: float, sr: float, catalog: dict | None = None) -> float:
    """
    NBCC 2015 roof snow load, kPa:  S = Is[Ss(Cb.Cw.Cs.Ca) + Sr].
    Residential defaults from catalog['snow'].
    """
    s = (catalog or _catalog())["snow"]
    accum = s["basic_roof_factor_cb"] * s["wind_exposure_cw"] \
        * s["slope_factor_cs"] * s["accumulation_factor_ca"]
    return s["importance_factor_uls"] * (ss * accum + sr)


def snow_tier(roof_load_kpa: float, catalog: dict | None = None) -> dict:
    """First tier whose max_roof_load_kpa the load fits under."""
    tiers = (catalog or _catalog())["snow"]["tiers"]
    for t in tiers:
        if roof_load_kpa <= t["max_roof_load_kpa"]:
            return t
    return tiers[-1]


@dataclass
class ResolvedLocation:
    name: str
    climate_zone: str          # "6" | "7a" | "7b"
    region: str                # key into catalog["regions"]
    region_name: str
    ss: float                  # ground snow load, kPa
    sr: float                  # associated rain load, kPa
    roof_snow_load_kpa: float  # computed S
    snow_tier: dict            # {id, name, joist_depth_in, ...}
    electricity_cad_per_kwh: float
    natural_gas_cad_per_kwh: float
    allowable_bearing_kpa: float
    frost_depth_m: float
    over_snow_range: bool      # True if S exceeds the top standard tier -> review

    @property
    def joist_depth_in(self) -> int:
        return self.snow_tier["joist_depth_in"]


def resolve(name: str) -> ResolvedLocation:
    locs = _locations()
    if name not in locs:
        raise KeyError(f"unknown location {name!r}")
    loc = locs[name]
    cat = _catalog()

    S = roof_snow_load(loc["ss"], loc["sr"], cat)
    tier = snow_tier(S, cat)
    region = cat["regions"][loc["region"]]

    return ResolvedLocation(
        name=name,
        climate_zone=loc["climate_zone"],
        region=loc["region"],
        region_name=region["name"],
        ss=loc["ss"],
        sr=loc["sr"],
        roof_snow_load_kpa=round(S, 2),
        snow_tier=tier,
        electricity_cad_per_kwh=region["electricity_cad_per_kwh"],
        natural_gas_cad_per_kwh=region["natural_gas_cad_per_kwh"],
        allowable_bearing_kpa=region["allowable_bearing_kpa"],
        frost_depth_m=region["frost_depth_m"],
        over_snow_range=S > 3.0,
    )
