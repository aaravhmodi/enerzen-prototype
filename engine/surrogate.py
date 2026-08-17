"""
Optional accuracy upgrade for engine/optimizer.py: for projects that match
the geometry the HOT2000 surrogate was trained on, replace
engine.simulator's degree-day approximation of EUI/TEDI with predictions
from a GBM trained directly on real HOT2000 output (verified within
0.2-0.4 kWh/m2/yr of real HOT2000 across the top-20 check — see
scripts/hot2000/HANDOFF.md).

Deliberately narrow ("ships today" scope, per user decision): the
surrogate only knows one house geometry (Toronto, ~153 m2, 2-storey,
south-facing — see TRAINED_GEOMETRY), one foundation type (slab-on-grade,
FA1), and one heating fuel (gas). Outside that envelope,
`applies_to()` returns False and optimizer.py keeps using simulator.py
unchanged. This is an accuracy trade, not a speed one — simulator.py is
already fast (~900 configs in ~0.2s); the point of the surrogate here is
that it's closer to what real HOT2000 would say for the geometry it was
trained on, not that it's faster.

Extending this to other geometries means retraining with floor_area/
storeys/orientation/climate_zone as additional features, which needs more
base .h2k files and a much bigger HOT2000 batch — not done here (see
HANDOFF.md option B).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

MODEL_DIR = Path(__file__).parent.parent / "data" / "hot2000" / "surrogate_models"

TRAINED_GEOMETRY = {
    "floor_area_m2": 153.0,
    "floor_area_tolerance_m2": 15.0,   # ~10% — the surrogate was trained at exactly 153 m2, not swept
    "storeys": 2,
    "orientation": "S",
    "climate_zone": "6",               # Toronto Intl
}

# Slab RSI isn't swept per-combo here: HOT2000's simplified "top of slab"
# model (what the surrogate was trained on) doesn't correspond cleanly to
# engine/foundation.py's perimeter-strip EPS model (see
# variant_generator.py's docstring for the same caveat). Using the
# midpoint of the trained range (0.35-3.0) rather than trying to map
# EPS_MM_OPTIONS to it.
DEFAULT_SLAB_RSI = 1.5

_models: Optional[dict] = None


def is_available() -> bool:
    return (MODEL_DIR / "eui_kwh_m2_yr.joblib").exists()


def _load_models() -> dict:
    global _models
    if _models is None:
        import joblib
        _models = {}
        for target in ("eui_kwh_m2_yr", "tedi_kwh_m2_yr", "peak_heating_load_w"):
            path = MODEL_DIR / f"{target}.joblib"
            _models[target] = joblib.load(path) if path.exists() else None
    return _models


def matches_trained_geometry(floor_area_m2: float, storeys: int, orientation: str,
                              climate_zone: str) -> bool:
    g = TRAINED_GEOMETRY
    return (
        abs(floor_area_m2 - g["floor_area_m2"]) <= g["floor_area_tolerance_m2"]
        and storeys == g["storeys"]
        and orientation == g["orientation"]
        and climate_zone == g["climate_zone"]
    )


@dataclass
class SurrogatePrediction:
    eui_kwh_m2_yr: float
    tedi_kwh_m2_yr: float
    peak_heating_load_w: float


def applies_to(spec, wall_id: str, roof_id: str, floor_id: str, mechanical_type: str) -> bool:
    """spec: engine.optimizer.ProjectSpec (or anything with the same
    floor_area_m2/storeys/orientation attributes). climate_zone must be
    resolved by the caller (location overrides spec.climate_zone)."""
    if not is_available():
        return False
    if wall_id not in ("WA1", "WA2") or roof_id not in ("RA1", "RA2"):
        return False
    if floor_id != "FA1":          # surrogate was trained on slab-on-grade only
        return False
    if mechanical_type != "gas":    # surrogate was trained on a gas furnace only
        return False
    return True


def predict(*, wall_id: str, wall_ext_rigid_in: float, roof_id: str, roof_deck_rigid_in: float,
            window_u_value: float, window_shgc: float,
            furnace_efficiency_pct: float) -> Optional[SurrogatePrediction]:
    """Raw features must match scripts/hot2000/train_surrogate.py's
    FEATURE_COLUMNS exactly (wall_type/roof_type as catalog IDs + rigid
    thickness in inches, not derived RSI — the model was trained on the
    catalog choice, not the resulting R-value)."""
    models = _load_models()
    if any(m is None for m in models.values()):
        return None

    import pandas as pd

    window_rsi = 1.0 / window_u_value
    row = pd.DataFrame([{
        "wall_ext_rigid_in": wall_ext_rigid_in,
        "roof_deck_rigid_in": roof_deck_rigid_in,
        "window_rsi": window_rsi,
        "window_shgc": window_shgc,
        "slab_rsi": DEFAULT_SLAB_RSI,
        "furnace_efficiency_pct": furnace_efficiency_pct,
        "wall_type_WA1": 1 if wall_id == "WA1" else 0,
        "wall_type_WA2": 1 if wall_id == "WA2" else 0,
        "roof_type_RA1": 1 if roof_id == "RA1" else 0,
        "roof_type_RA2": 1 if roof_id == "RA2" else 0,
    }])

    out = {}
    for target, bundle in models.items():
        model, feature_cols = bundle["model"], bundle["feature_cols"]
        X = row.reindex(columns=feature_cols, fill_value=0)
        out[target] = float(model.predict(X)[0])

    return SurrogatePrediction(
        eui_kwh_m2_yr=out["eui_kwh_m2_yr"],
        tedi_kwh_m2_yr=out["tedi_kwh_m2_yr"],
        peak_heating_load_w=out["peak_heating_load_w"],
    )
