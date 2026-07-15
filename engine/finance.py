"""
Utility bill and lifecycle cost estimates.

Monthly utility: annual energy demand from the simulator is distributed across
the year using typical Ontario monthly profiles (heating by HDD share, cooling
by CDD share, base loads flat, PV by irradiance share), then priced with the
retail rates in assemblies.json → energy_rates.

Lifecycle cost: upfront construction (less any solar rebate) plus the present
value of annual energy bills over the study period, with energy-price
escalation discounted back to today.
"""

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Typical Ontario monthly shares (normalized in _norm). Shape matters, not sum.
_HEATING_SHARE = [0.16, 0.14, 0.12, 0.08, 0.04, 0.01, 0.00, 0.00, 0.02, 0.07, 0.12, 0.15]
_COOLING_SHARE = [0.00, 0.00, 0.00, 0.00, 0.05, 0.20, 0.35, 0.30, 0.10, 0.00, 0.00, 0.00]
_SOLAR_SHARE   = [0.04, 0.06, 0.09, 0.11, 0.12, 0.12, 0.12, 0.11, 0.09, 0.06, 0.04, 0.03]


def _norm(shares):
    total = sum(shares)
    return [s / total for s in shares]


def monthly_utility(energy, mech_type: str, pv_generation_kwh: float, rates: dict) -> dict:
    """
    Args:
        energy: EnergyResult (heating/cooling/hot_water demand + total, kWh/yr)
        mech_type: "gas" or "electric" (determines how heating is billed)
        pv_generation_kwh: annual on-site PV generation
        rates: energy_rates block from the catalog

    Returns per-month electricity/gas costs and annual totals.
    """
    elec_rate = rates["electricity_cad_per_kwh"]
    gas_rate  = rates["natural_gas_cad_per_kwh"]
    # Fixed monthly customer charges: everyone pays the electricity service
    # charge; the gas charge applies only if the home has a gas connection.
    # This is why an all-electric home saves ~$300/yr before using a single kWh.
    elec_fixed = rates.get("electricity_fixed_monthly_cad", 0.0)
    gas_fixed  = rates.get("natural_gas_fixed_monthly_cad", 0.0)

    heat = _norm(_HEATING_SHARE)
    cool = _norm(_COOLING_SHARE)
    solar = _norm(_SOLAR_SHARE)

    # Base loads (hot water + appliances/lighting) are electric and roughly flat.
    base_annual = energy.total_energy_kwh_yr - energy.heating_demand_kwh_yr \
        - energy.cooling_demand_kwh_yr
    base_monthly = base_annual / 12

    heating_is_gas = mech_type == "gas"

    months = []
    annual_elec_cost = 0.0
    annual_gas_cost = 0.0
    annual_bill = 0.0

    for i, name in enumerate(MONTHS):
        heat_kwh = energy.heating_demand_kwh_yr * heat[i]
        cool_kwh = energy.cooling_demand_kwh_yr * cool[i]
        pv_kwh   = pv_generation_kwh * solar[i]

        # Electricity load: cooling + base + (heating if electric)
        elec_kwh = cool_kwh + base_monthly + (0 if heating_is_gas else heat_kwh)
        gas_kwh  = heat_kwh if heating_is_gas else 0.0

        # Net metering: PV offsets electricity in-month (energy floors at 0,
        # but the fixed service charge is always payable).
        net_elec_kwh = elec_kwh - pv_kwh
        elec_cost = max(net_elec_kwh, 0) * elec_rate + elec_fixed
        gas_cost  = gas_kwh * gas_rate + (gas_fixed if heating_is_gas else 0.0)

        annual_elec_cost += elec_cost
        annual_gas_cost += gas_cost
        annual_bill += elec_cost + gas_cost

        months.append({
            "month": name,
            "electricity": round(elec_cost, 0),
            "gas": round(gas_cost, 0),
            "total": round(elec_cost + gas_cost, 0),
        })

    return {
        "months": months,
        "annual_electricity_cost": round(annual_elec_cost, 0),
        "annual_gas_cost": round(annual_gas_cost, 0),
        "annual_total": round(annual_bill, 0),
        "avg_monthly": round(annual_bill / 12, 0),
    }


def lifecycle_cost(construction_cost: float, annual_energy_cost: float,
                   rebate: float = 0.0, years: int = 30,
                   discount_rate: float = 0.03, energy_escalation: float = 0.02) -> dict:
    """
    Present-value lifecycle cost: upfront capital (less rebate) plus discounted
    energy bills over the study period.
    """
    upfront = construction_cost - rebate

    pv_energy = 0.0
    for yr in range(1, years + 1):
        escalated = annual_energy_cost * (1 + energy_escalation) ** (yr - 1)
        pv_energy += escalated / (1 + discount_rate) ** yr

    return {
        "upfront": round(upfront, 0),
        "energy_pv": round(pv_energy, 0),
        "total": round(upfront + pv_energy, 0),
        "years": years,
    }
