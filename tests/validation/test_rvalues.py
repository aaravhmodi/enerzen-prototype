"""TRL 5 validation: effective R-values against the National Building Code
method (A-9.36.2.4), using two published City of Moncton worksheets:

- MW-03: 2x6 @ 16" o.c., RSI 3.87 (R-22) batt, 11.1 mm OSB, vinyl siding,
  12.7 mm gypsum -> RSI 3.00 effective.
- MW-02: as above with RSI 3.34 (R-20) batt and 12.7 mm XPS -> RSI 3.25.

https://www5.moncton.ca/docs/bi/MW-03_Fiberglass_Batt.pdf
https://www5.moncton.ca/docs/bi/MW-02_Extruded_Polystyrene_and_Fiberglass_Batt.pdf
Results and discussion: docs/TRL5_VALIDATION_RESULTS.md.
"""

import pytest

from engine.rvalue import Assembly, FramedCavity, Layer

CASES = {
    "MW-03": (3.00, Assembly("MW-03", "wall",
                             [Layer("vinyl_siding", 1), Layer("osb", 0.4375), Layer("gypsum", 0.5)],
                             FramedCavity("mineral_wool_batt", 5.5, framing_factor=0.23))),
    "MW-02": (3.25, Assembly("MW-02", "wall",
                             [Layer("vinyl_siding", 1), Layer("xps", 0.5), Layer("osb", 0.4375),
                              Layer("gypsum", 0.5)],
                             FramedCavity("fiberglass_batt", 5.5, framing_factor=0.23))),
}


def nbc_effective_rsi(assembly: Assembly) -> float:
    """NBC A-9.36.2.4 (isothermal planes): parallel path within the framed
    layer only, then the continuous layers and air films in series."""
    ff = assembly.cavity.framing_factor
    framed = 1 / (ff / assembly.cavity.rsi_framing + (1 - ff) / assembly.cavity.rsi_cavity)
    return assembly.rsi_continuous + framed


@pytest.mark.parametrize("case", CASES)
def test_engine_material_values_reproduce_the_code_worksheets(case):
    published, assembly = CASES[case]
    assert nbc_effective_rsi(assembly) == pytest.approx(published, rel=0.01)


@pytest.mark.parametrize("case", CASES)
def test_engine_effective_rsi_matches_the_code(case):
    published, assembly = CASES[case]
    assert assembly.rsi_effective == pytest.approx(published, rel=0.01)
