"""
Trains GBM surrogate models on the HOT2000 training data produced by
sample_and_run.py — one model per target (EUI, TEDI, peak heating load),
predicting in milliseconds what a real HOT2000 run takes ~7s to produce.

Uses sklearn's HistGradientBoostingRegressor (no extra dependency — the
project already has scikit-learn; lightgbm is not installed and wasn't
added, since sklearn's histogram GBM is the same family of algorithm and
plenty fast for a dataset this size).

Usage:
    python -m scripts.hot2000.train_surrogate --data data/hot2000/training_data.csv

Run with the normal (64-bit) project Python — this script only touches
the CSV, not HOT2000, so it doesn't need the 32-bit interpreter.
"""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

FEATURE_COLUMNS = [
    "wall_type", "wall_ext_rigid_in", "roof_type", "roof_deck_rigid_in",
    "window_rsi", "window_shgc", "slab_rsi", "furnace_efficiency_pct",
]
TARGET_COLUMNS = ["eui_kwh_m2_yr", "tedi_kwh_m2_yr", "peak_heating_load_w"]

MODEL_DIR = Path(__file__).parent.parent.parent / "data" / "hot2000" / "surrogate_models"


def load_training_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    before = len(df)
    df = df[df["error"].isna() | (df["error"] == "")]
    dropped = before - len(df)
    if dropped:
        print(f"Dropped {dropped}/{before} failed HOT2000 runs")

    # wall_type / roof_type are categorical (WA1/WA2, RA1/RA2) — one-hot encode.
    df = pd.get_dummies(df, columns=["wall_type", "roof_type"])
    return df


def train_one(df: pd.DataFrame, target: str, feature_cols: list[str]) -> dict:
    X = df[feature_cols]
    y = df[target]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=0)

    model = HistGradientBoostingRegressor(random_state=0)
    model.fit(X_train, y_train)

    pred = model.predict(X_test)
    r2 = r2_score(y_test, pred)
    mae = mean_absolute_error(y_test, pred)
    print(f"{target}: R2={r2:.3f}  MAE={mae:.2f}  (n_train={len(X_train)}, n_test={len(X_test)})")

    return {"model": model, "feature_cols": feature_cols, "r2": r2, "mae": mae}


def train_all(csv_path: Path, model_dir: Path = MODEL_DIR):
    df = load_training_data(csv_path)
    if len(df) < 50:
        print(f"WARNING: only {len(df)} usable rows — surrogate quality will be poor. "
              f"Run more samples via sample_and_run.py before trusting this model.")

    dummy_cols = [c for c in df.columns if c.startswith("wall_type_") or c.startswith("roof_type_")]
    feature_cols = [c for c in FEATURE_COLUMNS if c in df.columns and c not in ("wall_type", "roof_type")] + dummy_cols

    model_dir.mkdir(parents=True, exist_ok=True)
    metrics = {}
    for target in TARGET_COLUMNS:
        result = train_one(df, target, feature_cols)
        joblib.dump(
            {"model": result["model"], "feature_cols": result["feature_cols"]},
            model_dir / f"{target}.joblib",
        )
        metrics[target] = {"r2": result["r2"], "mae": result["mae"], "n": len(df)}

    (model_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nModels saved to {model_dir}")


def predict(samples: pd.DataFrame, model_dir: Path = MODEL_DIR) -> pd.DataFrame:
    """samples: DataFrame with the same raw columns as sample_and_run.py's
    sample dicts (wall_type, wall_ext_rigid_in, ... — pre-one-hot)."""
    samples = pd.get_dummies(samples, columns=["wall_type", "roof_type"])
    out = {}
    for target in TARGET_COLUMNS:
        bundle = joblib.load(model_dir / f"{target}.joblib")
        model, feature_cols = bundle["model"], bundle["feature_cols"]
        X = samples.reindex(columns=feature_cols, fill_value=0)
        out[target] = model.predict(X)
    return pd.DataFrame(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/hot2000/training_data.csv"))
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    args = parser.parse_args()

    if not args.data.exists():
        raise SystemExit(f"{args.data} doesn't exist yet — run sample_and_run.py first")

    train_all(args.data, args.model_dir)
