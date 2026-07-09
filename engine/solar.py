"""
Rooftop PV generation, cost, and carbon.

Annual generation uses a specific-yield model: a fixed-tilt, roughly
south-facing array in Ontario produces `solar_yield_kwh_per_kwp` kWh per
installed kWp per year (from assemblies.json, per climate zone). Orientation
applies a modest derate — an east/west main facade implies a less ideal roof
plane than a south-facing one.
"""

# Generation derate by main-facade orientation (proxy for roof plane aspect).
ORIENTATION_FACTOR = {"S": 1.00, "E": 0.90, "W": 0.90, "N": 0.80}


def calculate_solar(solar_option: dict, climate: dict, orientation: str) -> dict:
    """
    Args:
        solar_option: one entry from catalog["solar"]
        climate: the climate_zones[...] entry (needs solar_yield_kwh_per_kwp)
        orientation: main facade orientation, "N"/"S"/"E"/"W"

    Returns dict with capacity, annual generation, cost, embodied carbon.
    """
    capacity_kw = solar_option["capacity_kw"]
    specific_yield = climate.get("solar_yield_kwh_per_kwp", 1200)
    derate = ORIENTATION_FACTOR.get(orientation, 0.90)

    annual_generation = capacity_kw * specific_yield * derate

    cost = capacity_kw * solar_option["cost_per_kw"]
    embodied = capacity_kw * solar_option["embodied_carbon_kg_co2e_per_kw"]

    return {
        "capacity_kw": capacity_kw,
        "annual_generation_kwh": round(annual_generation, 0),
        "cost": round(cost, 0),
        "embodied_carbon_kg_co2e": round(embodied, 0),
    }
