"""
Class D soft costs and the soft (pre-construction) timeline.

Defaults until EnerZen supplies its own allowances. Each value names its
source; see METHODOLOGY.md section 6.9.
"""

from dataclasses import asdict, dataclass

# Consultants, permits and development charges, legal, insurance and
# financing carry, as a share of hard construction cost. A widely used GTA
# pro forma rule of thumb (~25%); CMHC treats these as a separate cost line.
SOFT_COST_FRACTION = 0.25

# Design and engineering duration: an EnerZen default assumption, not sourced.
DESIGN_WEEKS_SMALL = 8
DESIGN_WEEKS_LARGE = 16

# Ontario Building Code permit review periods for complete applications,
# in business days: houses 10, Part 9 row houses and small buildings 15,
# Part 3 buildings (over 3 storeys or over 600 m2) 20.
PERMIT_DAYS = {"house": 10, "part9": 15, "part3": 20}

# Planning Act: site plan approval within 60 days (Bill 109); residential
# developments of 10 or fewer units are exempt from site plan control (Bill 23).
SITE_PLAN_DAYS = 60
SITE_PLAN_EXEMPT_MAX_UNITS = 10


@dataclass
class SoftTimeline:
    design_engineering_weeks: float
    site_plan_weeks: float
    building_permit_weeks: float
    total_weeks: float
    permit_class: str
    site_plan_exempt: bool

    def as_dict(self) -> dict:
        return asdict(self)


def soft_cost(hard_cost: float) -> float:
    return round(hard_cost * SOFT_COST_FRACTION)


def permit_class(typology: str, storeys: int, building_area_m2: float) -> str:
    if storeys > 3 or building_area_m2 > 600:
        return "part3"
    if typology in ("townhouse", "murb"):
        return "part9"
    return "house"


def soft_timeline(typology: str, storeys: int, building_area_m2: float, total_units: int) -> SoftTimeline:
    """Weeks from brief to building permit, assuming complete applications
    and no zoning amendment (unknown until a parcel is selected)."""
    pclass = permit_class(typology, storeys, building_area_m2)
    large = pclass == "part3" or total_units > SITE_PLAN_EXEMPT_MAX_UNITS
    design = DESIGN_WEEKS_LARGE if large else DESIGN_WEEKS_SMALL
    exempt = total_units <= SITE_PLAN_EXEMPT_MAX_UNITS
    site_plan = 0.0 if exempt else SITE_PLAN_DAYS / 7
    permit = PERMIT_DAYS[pclass] / 5
    return SoftTimeline(
        design_engineering_weeks=design,
        site_plan_weeks=round(site_plan, 1),
        building_permit_weeks=round(permit, 1),
        total_weeks=round(design + site_plan + permit, 1),
        permit_class=pclass,
        site_plan_exempt=exempt,
    )
