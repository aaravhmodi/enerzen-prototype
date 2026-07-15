# EnerZen Performance Engine

Prototype optimization platform for EnerZen's industrialized high-performance housing system.

## What it does

Takes a building project's specifications and returns the best combination of wall panels, floor cassettes, and roof cassettes from EnerZen's assembly catalog — optimized across construction cost, build time, embodied carbon, and operational energy simultaneously.

## Run locally

```bash
pip install -r requirements.txt
streamlit run ui/app.py
```

## Structure

```
engine/       # Core optimization logic
  simulator.py    # Energy model (HOT2000-style degree-day)
  optimizer.py    # Multi-objective Pareto optimizer
  carbon.py       # Embodied + operational carbon
  cost.py         # Cost estimator + panel schedule
  materials.py    # Material table: R, cost, carbon per inch (one source of truth)
  rvalue.py       # Parallel-path effective R-value engine
  assemblies.py   # The 6 layer-defined parametric assemblies
  location.py     # Ontario location resolver (climate, snow, rates, soil)
data/
  assemblies.json # Windows, mechanical, solar, climate, rates, regions, snow
  ontario_locations.json # 227 Ontario locations (snow loads, regions)
ui/
  app.py          # Streamlit interface
```
