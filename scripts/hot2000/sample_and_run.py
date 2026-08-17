"""
Samples the design space, generates a .h2k variant per sample, runs it
through real HOT2000, and appends inputs + outputs to a CSV — the training
set for the GBM surrogate.

Design space (continuous, wider than optimizer.py's coarse 0/2/4" grid —
the point of the surrogate is to cover ground the brute-force optimizer
can't afford to):
  wall_type         WA1 | WA2                          (engine.assemblies.WALLS)
  wall_ext_rigid_in  0.0 - 6.0"
  roof_type         RA1 | RA2                          (engine.assemblies.ROOFS)
  roof_deck_rigid_in 0.0 - 6.0"
  window_rsi        0.5 - 1.4 m2K/W  (~U 0.7-2.0, code-min to triple-pane)
  window_shgc       0.20 - 0.65
  slab_rsi          0.35 - 3.0 m2K/W (HOT2000's top-of-slab model — see
                     variant_generator.py docstring for the caveat that
                     this doesn't match engine/foundation.py's perimeter-EPS
                     model exactly)
  furnace_efficiency_pct  80 - 97

NOT sampled yet (left at base-file defaults — see HANDOFF.md gotcha #the
blower-door-pressure one): infiltration/ACH, floor area, storeys,
orientation, climate zone. Extending the sampler to cover those needs
either more base house files (different storeys/orientation are cheap to
re-derive from the wizard flow) or geometry-editing XML work this session
didn't get to.

Usage:
    C:/Python311-32/python.exe -m scripts.hot2000.sample_and_run --n 200 --out data/hot2000/training_data.csv

Writes rows incrementally (one HOT2000 crash or bad sample doesn't lose
earlier results — important for an overnight run).
"""

import argparse
import csv
import random
import time
from pathlib import Path

from engine.assemblies import WALLS, ROOFS
from scripts.hot2000.runner import Hot2000Runner
from scripts.hot2000.variant_generator import VariantParams, generate_variant

VARIANTS_DIR = Path(__file__).parent.parent.parent / "data" / "hot2000" / "variants"

INPUT_FIELDS = [
    "wall_type", "wall_ext_rigid_in", "roof_type", "roof_deck_rigid_in",
    "window_rsi", "window_shgc", "slab_rsi", "furnace_efficiency_pct",
]
OUTPUT_FIELDS = [
    "eui_kwh_m2_yr", "tedi_kwh_m2_yr", "heating_demand_kwh_yr",
    "peak_heating_load_w", "peak_cooling_load_w",
]


def sample_one(rng: random.Random) -> dict:
    wall_type = rng.choice(["WA1", "WA2"])
    roof_type = rng.choice(["RA1", "RA2"])
    return {
        "wall_type": wall_type,
        "wall_ext_rigid_in": round(rng.uniform(0.0, 6.0), 2),
        "roof_type": roof_type,
        "roof_deck_rigid_in": round(rng.uniform(0.0, 6.0), 2),
        "window_rsi": round(rng.uniform(0.5, 1.4), 3),
        "window_shgc": round(rng.uniform(0.20, 0.65), 3),
        "slab_rsi": round(rng.uniform(0.35, 3.0), 3),
        "furnace_efficiency_pct": round(rng.uniform(80, 97), 1),
    }


def sample_to_variant_params(sample: dict) -> VariantParams:
    wall_builder = WALLS[0] if sample["wall_type"] == "WA1" else WALLS[1]
    roof_builder = ROOFS[0] if sample["roof_type"] == "RA1" else ROOFS[1]

    wall_asm = wall_builder.build(sample["wall_ext_rigid_in"])
    # joist depth fixed at 10" (matches base template's snow-tier default;
    # not swept — see module docstring for what's not covered yet)
    roof_asm = roof_builder.build(10, sample["roof_deck_rigid_in"])

    return VariantParams(
        wall_rsi=wall_asm.rsi_effective,
        ceiling_rsi=roof_asm.rsi_effective,
        window_rsi=sample["window_rsi"],
        window_shgc=sample["window_shgc"],
        slab_rsi=sample["slab_rsi"],
        furnace_efficiency_pct=sample["furnace_efficiency_pct"],
    )


def run(n: int, out_csv: Path, seed: int = 0):
    rng = random.Random(seed)
    VARIANTS_DIR.mkdir(parents=True, exist_ok=True)

    write_header = not out_csv.exists()
    csv_file = open(out_csv, "a", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=INPUT_FIELDS + OUTPUT_FIELDS + ["error"])
    if write_header:
        writer.writeheader()

    runner = Hot2000Runner()
    runner.launch()
    try:
        for i in range(n):
            sample = sample_one(rng)
            variant_path = VARIANTS_DIR / f"variant_{i:05d}.h2k"
            generate_variant(sample_to_variant_params(sample), variant_path)

            row = dict(sample)
            print(f"[{i+1}/{n}] {variant_path.name}", end=" ")
            try:
                result = runner.run_one(variant_path)
                row.update({
                    "eui_kwh_m2_yr": result.eui_kwh_m2_yr,
                    "tedi_kwh_m2_yr": result.tedi_kwh_m2_yr,
                    "heating_demand_kwh_yr": result.heating_demand_kwh_yr,
                    "peak_heating_load_w": result.peak_heating_load_w,
                    "peak_cooling_load_w": result.peak_cooling_load_w,
                    "error": "",
                })
                print(f"EUI={result.eui_kwh_m2_yr:.1f}")
            except Exception as e:
                # Broad on purpose: an overnight run must survive pywinauto
                # timing races (ElementNotEnabled etc.), not just the
                # Hot2000Error cases we anticipated. Log and keep going.
                row["error"] = f"{type(e).__name__}: {e}"
                print(f"FAILED: {row['error']}")
                try:
                    runner.close_file()
                except Exception:
                    # The runner itself may be wedged — nuke the process and
                    # start a fresh HOT2000 session rather than losing the
                    # rest of the batch.
                    print("  runner looks stuck — restarting HOT2000")
                    try:
                        runner.quit()
                    except Exception:
                        pass
                    import subprocess
                    subprocess.run(["taskkill", "/IM", "HOT2000.exe", "/F"], capture_output=True)
                    time.sleep(1)
                    runner = Hot2000Runner()
                    runner.launch()

            writer.writerow(row)
            csv_file.flush()
    finally:
        runner.quit()
        csv_file.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--out", type=Path, default=Path("data/hot2000/training_data.csv"))
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    start = time.time()
    run(args.n, args.out, args.seed)
    elapsed = time.time() - start
    print(f"\nDone: {args.n} samples in {elapsed/60:.1f} min ({elapsed/max(args.n,1):.1f}s/sample)")
