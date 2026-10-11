"""Display units for the drawings and the report.

The engine computes and stores everything in SI. A `Units` only formats those
numbers for people, in metric or imperial; nothing here feeds a calculation.
"""

SQFT_PER_M2 = 10.7639
FT_PER_M = 3.28084
PSF_PER_KPA = 20.8854
CUYD_PER_M3 = 1.30795

METRIC = "metric"
IMPERIAL = "imperial"


def _num(value: float, digits: int) -> str:
    """A number to at most `digits` decimals, without trailing zeros."""
    text = f"{value:,.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


class Units:
    def __init__(self, system: str = METRIC):
        self.imperial = system == IMPERIAL
        self.system = IMPERIAL if self.imperial else METRIC
        self.length_unit = "ft" if self.imperial else "m"
        self.area_unit = "sq ft" if self.imperial else "m2"

    def length_number(self, metres: float) -> str:
        return _num(metres * FT_PER_M, 1) if self.imperial else _num(metres, 2)

    def length(self, metres: float) -> str:
        return f"{self.length_number(metres)} {self.length_unit}"

    def dims(self, *metres: float, sep: str = " x ") -> str:
        """Several lengths sharing one unit, e.g. a lot's width and depth."""
        return f"{sep.join(self.length_number(m) for m in metres)} {self.length_unit}"

    def area(self, m2: float) -> str:
        if self.imperial:
            return f"{m2 * SQFT_PER_M2:,.0f} sq ft"
        return f"{_num(m2, 0 if m2 >= 100 else 1)} m2"

    def volume(self, m3: float) -> str:
        return f"{_num(m3 * CUYD_PER_M3, 1)} cu yd" if self.imperial else f"{_num(m3, 2)} m3"

    def pressure(self, kpa: float) -> str:
        return f"{kpa * PSF_PER_KPA:,.0f} psf" if self.imperial else f"{_num(kpa, 2)} kPa"

    def per_area(self, value: float) -> float:
        """A per-m2 quantity (cost, energy, carbon) per unit of display area."""
        return value / SQFT_PER_M2 if self.imperial else value

    def intensity(self, per_m2: float) -> str:
        """The number alone for a per-area intensity such as EUI or carbon."""
        return _num(self.per_area(per_m2), 2 if self.imperial else 1)

    def eui(self, kwh_m2_yr: float) -> str:
        return f"{self.intensity(kwh_m2_yr)} kWh/{self.area_unit}/yr"

    def carbon(self, kg_m2: float) -> str:
        return f"{self.intensity(kg_m2)} kgCO2e/{self.area_unit}"
