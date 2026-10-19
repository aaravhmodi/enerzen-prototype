"""
Utility bill and lifecycle cost estimates.

Monthly utility: annual energy demand from the simulator is distributed across
the year using typical Ontario monthly profiles (heating by HDD share, cooling
by CDD share, base loads flat, PV by irradiance share), then priced with the
retail rates in assemblies.json → energy_rates.

Lifecycle cost: upfront construction (less any solar rebate) plus the present
value of annual energy bills over the study period, with energy-price
escalation discounted back to today.

Rental pro forma: market rent from CMHC's survey and the MLI Select financing
the building's energy performance reaches (rental_pro_forma).
"""
import math

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


# CMHC Rental Market Survey, October 2025 (Toronto CMA data tables). A new lease in Pickering is priced
# from the asking rents of vacant apartments in Zone 28, Pickering/Ajax/Uxbridge (table 1.1.9); CMHC
# suppresses the zone's studio and 1-bedroom figures, so those are Durham Region's.
CMHC_RENTS = {
    'source': 'CMHC Rental Market Survey, October 2025 (Toronto CMA tables 1.1.1, 1.1.9, 1.2.2)',
    'url': 'https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-data/'
           'data-tables/rental-market/rental-market-report-data-tables',
    'monthly_by_bedrooms': {0: 1462, 1: 1661, 2: 2091, 3: 2403},
    'area_by_bedrooms': {0: 'Durham Region', 1: 'Durham Region', 2: 'Pickering/Ajax/Uxbridge',
                         3: 'Pickering/Ajax/Uxbridge'},
    # Apartments built 2015 or later in the CMA's suburban zones (18-31): what newer buildings lease for.
    'new_building_monthly_by_bedrooms': {0: 1746, 1: 2197, 2: 2813, 3: 3131},
    'vacancy_rate': 0.018,  # Zone 28, all apartments
}

# CMHC MLI Select for new construction (cmhc-schl.gc.ca, page of 2026-09-21). Energy is measured against
# NBC 2020 Tier 1 (Part 9) by a qualified energy modeller.
MLI_SELECT = {
    'url': 'https://www.cmhc-schl.gc.ca/professionals/project-funding-and-mortgage-financing/'
           'mortgage-loan-insurance/multi-unit-insurance/mliselect',
    'min_homes': 5,
    'energy_points': [(0.20, 20), (0.40, 35), (0.70, 50)],  # share better than NBC 2020 Tier 1
    'affordability_points': [(0.10, 50), (0.15, 70), (0.25, 100)],  # share of homes at 30% of median renter income, 10 years
    'accessibility_points': [('15% of homes accessible (CSA B651:23)', 20), ('100% universal design', 30)],
    'tiers': [{'points': 50, 'amortization_years': 40, 'max_loan_to_cost': 0.95},
              {'points': 70, 'amortization_years': 45, 'max_loan_to_cost': 0.95},
              {'points': 100, 'amortization_years': 50, 'max_loan_to_cost': 0.95, 'limited_recourse': True}],
    'min_dcr': 1.10,
}


def rental_pro_forma(homes_by_bedrooms: dict, total_project_cost: float, eui: float, code_eui: float) -> dict:
    """Market rent for these homes and what MLI Select financing their energy performance reaches.
    `homes_by_bedrooms` is {bedrooms: homes}; 3 stands for 3 or more."""
    homes = {}
    for b, n in homes_by_bedrooms.items():
        homes[min(b, 3)] = homes.get(min(b, 3), 0) + n
    count = sum(homes.values())
    monthly = sum(n * CMHC_RENTS['monthly_by_bedrooms'][b] for b, n in homes.items())
    new_monthly = sum(n * CMHC_RENTS['new_building_monthly_by_bedrooms'][b] for b, n in homes.items())
    gross = 12 * monthly
    # shortcut: screens against a code-built home's EUI, not an NBC 2020 Tier 1 model of this building.
    better = max(0.0, 1 - eui / code_eui) if code_eui else 0.0
    energy = max((p for share, p in MLI_SELECT['energy_points'] if better >= share), default=0)
    return {
        'homes': count, 'monthly_rent': round(monthly), 'annual_gross_rent': round(gross),
        'vacancy_rate': CMHC_RENTS['vacancy_rate'],
        'annual_effective_rent': round(gross * (1 - CMHC_RENTS['vacancy_rate'])),
        'new_building_monthly_rent': round(new_monthly),
        'rents_used': {b: {'monthly': CMHC_RENTS['monthly_by_bedrooms'][b], 'area': CMHC_RENTS['area_by_bedrooms'][b],
                           'homes': n} for b, n in sorted(homes.items()) if n},
        'gross_yield_on_cost': round(gross / total_project_cost, 4) if total_project_cost else None,
        'source': CMHC_RENTS['source'], 'url': CMHC_RENTS['url'],
        'mli_select': {
            'eligible': count >= MLI_SELECT['min_homes'],
            'energy_better_than_code': round(better, 3), 'energy_points': energy,
            # The fewest affordable homes that reach each affordability level.
            'affordability_options': [{'homes': math.ceil(round(count * share, 6)), 'points': p}
                                      for share, p in MLI_SELECT['affordability_points']],
            'accessibility_options': [{'option': o, 'points': p} for o, p in MLI_SELECT['accessibility_points']],
            'tiers': MLI_SELECT['tiers'], 'min_dcr': MLI_SELECT['min_dcr'],
            'max_loan_at_50_points': round(MLI_SELECT['tiers'][0]['max_loan_to_cost'] * total_project_cost),
            'url': MLI_SELECT['url'],
        },
    }
