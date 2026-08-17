"""
The payoff for the whole pipeline: search a much wider, continuous design
space with the trained GBM surrogate (milliseconds for thousands of
candidates), rank by a simple weighted score, then re-run only the top N
through *real* HOT2000 — so every number that actually gets reported traces
back to a genuine simulation run, not the surrogate's approximation.

This intentionally stays a standalone script rather than being folded into
engine/optimizer.py's ConfigResult/cost/carbon/schedule pipeline yet — that
pipeline is keyed on the coarse WA1/WA2/RA1/RA2/FA1/FA2 catalog IDs and
their 0/2/4" sweep, whereas the surrogate searches continuous
wall_ext_rigid_in / roof_deck_rigid_in / window RSI+SHGC / slab RSI /
furnace efficiency (see sample_and_run.py's design space). Wiring the two
together — i.e. having optimizer.py call this for the final ranking instead
of simulator.py — is the next real step; this script proves the mechanism
end to end first.

Usage (surrogate search needs pandas/sklearn — normal 64-bit Python; the
real-HOT2000 verification step needs pywinauto — 32-bit Python. Note: the
32-bit interpreter can't build pandas from source here (no MSVC build
tools, no prebuilt wheel), so `verify()` and the CLI's verify path
deliberately avoid pandas entirely and use stdlib csv):

    python -m scripts.hot2000.surrogate_optimize --search-only --n-candidates 20000
    # writes data/hot2000/surrogate_search_top20.csv

    C:/Python311-32/python.exe -m scripts.hot2000.surrogate_optimize --verify-only
    # reads that CSV, re-runs the 20 through real HOT2000, writes
    # data/hot2000/surrogate_search_verified.csv with both predicted and
    # real numbers side by side
"""

import argparse
import csv
import random
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "hot2000"
TOP_N_PATH = DATA_DIR / "surrogate_search_top20.csv"
VERIFIED_PATH = DATA_DIR / "surrogate_search_verified.csv"

CANDIDATE_FIELDS = [
    "wall_type", "wall_ext_rigid_in", "roof_type", "roof_deck_rigid_in",
    "window_rsi", "window_shgc", "slab_rsi", "furnace_efficiency_pct",
]


def sample_candidates(n: int, seed: int = 123) -> list[dict]:
    """Same design space as sample_and_run.py, but a much larger n than any
    real-HOT2000 batch could afford — this is the whole point of having a
    surrogate."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        rows.append({
            "wall_type": rng.choice(["WA1", "WA2"]),
            "wall_ext_rigid_in": round(rng.uniform(0.0, 6.0), 2),
            "roof_type": rng.choice(["RA1", "RA2"]),
            "roof_deck_rigid_in": round(rng.uniform(0.0, 6.0), 2),
            "window_rsi": round(rng.uniform(0.5, 1.4), 3),
            "window_shgc": round(rng.uniform(0.20, 0.65), 3),
            "slab_rsi": round(rng.uniform(0.35, 3.0), 3),
            "furnace_efficiency_pct": round(rng.uniform(80, 97), 1),
        })
    return rows


def search(n_candidates: int, top_n: int = 20) -> list[dict]:
    """64-bit only — needs pandas + the sklearn-backed predict()."""
    import pandas as pd
    from scripts.hot2000.train_surrogate import predict, MODEL_DIR

    if not (MODEL_DIR / "eui_kwh_m2_yr.joblib").exists():
        raise SystemExit("No trained surrogate found — run train_surrogate.py first")

    candidates = pd.DataFrame(sample_candidates(n_candidates))
    preds = predict(candidates)
    scored = pd.concat([candidates, preds], axis=1)

    # Simple weighted score: lower EUI and lower peak load are both better.
    # (No cost/carbon term yet — those aren't surrogate targets, they're
    # already fast closed-form calcs in engine/cost.py and engine/carbon.py;
    # folding them in is part of the optimizer.py integration, not this
    # proof-of-mechanism script.)
    eui_norm = (scored["eui_kwh_m2_yr"] - scored["eui_kwh_m2_yr"].min()) / (
        scored["eui_kwh_m2_yr"].max() - scored["eui_kwh_m2_yr"].min())
    peak_norm = (scored["peak_heating_load_w"] - scored["peak_heating_load_w"].min()) / (
        scored["peak_heating_load_w"].max() - scored["peak_heating_load_w"].min())
    scored["score"] = 0.5 * eui_norm + 0.5 * peak_norm

    top = scored.nsmallest(top_n, "score").reset_index(drop=True)
    return top.to_dict(orient="records")


def verify(top_rows: list[dict]) -> list[dict]:
    """Re-run the top candidates through real HOT2000. Must be called with
    32-bit Python (imports runner.py, which drives the GUI). Pandas-free —
    see module docstring for why."""
    from scripts.hot2000.runner import Hot2000Runner
    from scripts.hot2000.variant_generator import VariantParams, generate_variant
    from engine.assemblies import WALLS, ROOFS

    variants_dir = DATA_DIR / "verify_variants"
    variants_dir.mkdir(parents=True, exist_ok=True)

    runner = Hot2000Runner()
    runner.launch()
    out_rows = []
    try:
        for i, row in enumerate(top_rows):
            wall_builder = WALLS[0] if row["wall_type"] == "WA1" else WALLS[1]
            roof_builder = ROOFS[0] if row["roof_type"] == "RA1" else ROOFS[1]
            wall_asm = wall_builder.build(float(row["wall_ext_rigid_in"]))
            roof_asm = roof_builder.build(10, float(row["roof_deck_rigid_in"]))

            params = VariantParams(
                wall_rsi=wall_asm.rsi_effective,
                ceiling_rsi=roof_asm.rsi_effective,
                window_rsi=float(row["window_rsi"]),
                window_shgc=float(row["window_shgc"]),
                slab_rsi=float(row["slab_rsi"]),
                furnace_efficiency_pct=float(row["furnace_efficiency_pct"]),
            )
            variant_path = variants_dir / f"top_{i:02d}.h2k"
            generate_variant(params, variant_path)

            out_row = dict(row)
            print(f"[{i+1}/{len(top_rows)}] verifying against real HOT2000...", end=" ")
            try:
                result = runner.run_one(variant_path)
                out_row["real_eui_kwh_m2_yr"] = result.eui_kwh_m2_yr
                out_row["real_tedi_kwh_m2_yr"] = result.tedi_kwh_m2_yr
                out_row["real_peak_heating_load_w"] = result.peak_heating_load_w
                out_row["verify_error"] = ""
                print(f"real EUI={result.eui_kwh_m2_yr:.1f} (predicted {float(row['eui_kwh_m2_yr']):.1f})")
            except Exception as e:
                out_row["verify_error"] = f"{type(e).__name__}: {e}"
                print(f"FAILED: {out_row['verify_error']}")
                try:
                    runner.close_file()
                except Exception:
                    pass
            out_rows.append(out_row)
    finally:
        runner.quit()

    return out_rows


def _write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-candidates", type=int, default=20000)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--search-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    if not args.verify_only:
        top = search(args.n_candidates, args.top_n)
        _write_csv(TOP_N_PATH, top)
        print(f"Searched {args.n_candidates} candidates, wrote top {args.top_n} to {TOP_N_PATH}")
        for row in top:
            print(f"  {row['wall_type']} ext={row['wall_ext_rigid_in']:.2f}in  "
                  f"{row['roof_type']} deck={row['roof_deck_rigid_in']:.2f}in  "
                  f"EUI={row['eui_kwh_m2_yr']:.1f}  peak={row['peak_heating_load_w']:.0f}W  "
                  f"score={row['score']:.4f}")

    if not args.search_only:
        if not TOP_N_PATH.exists():
            raise SystemExit(f"{TOP_N_PATH} doesn't exist — run --search-only first (64-bit Python)")
        top = _read_csv(TOP_N_PATH)
        verified = verify(top)
        _write_csv(VERIFIED_PATH, verified)
        print(f"\nVerified results written to {VERIFIED_PATH}")
