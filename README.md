# EnerZen Performance Engine

Optimization platform for EnerZen's industrialized high-performance housing system.

## What it does

Takes a building project's specifications and returns the best combination of wall panels, floor cassettes, and roof cassettes from EnerZen's assembly catalog — optimized across construction cost, build time, embodied carbon, and operational energy simultaneously. It also computes a passive-solar-optimized **site plan**: where the building and driveway sit on a given lot, respecting setbacks and maximizing solar gain for the fixed building orientation.

An OpenAI integration (`engine/ai.py`) lets users describe a project in plain language and get a pre-filled spec, and can generate an illustrative concept rendering of the site plan alongside the authoritative technical diagram.

## Run locally

**Backend (engine + API)**

```bash
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_KEY
uvicorn api.main:app --reload --port 8001
```

**Frontend**

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000. The frontend expects the API at `http://localhost:8001` (see `web/.env.local`).

**Legacy Streamlit UI** (kept temporarily as a reference during the migration to `api/` + `web/`; does not have the site-plan feature):

```bash
streamlit run ui/app.py
```

## Structure

```
engine/       # Core optimization + siting logic
  simulator.py    # Energy model (HOT2000-style degree-day)
  optimizer.py    # Multi-objective Pareto optimizer
  carbon.py       # Embodied + operational carbon
  cost.py         # Cost estimator + panel schedule
  materials.py    # Material table: R, cost, carbon per inch (one source of truth)
  rvalue.py       # Parallel-path effective R-value engine
  assemblies.py   # The 6 layer-defined parametric assemblies
  location.py     # Ontario location resolver (climate, snow, rates, soil)
  site.py         # Passive-solar site placement engine + SVG renderer
  ai.py           # OpenAI: freeform spec parsing, design rationale, concept renders
  report.py       # Per-project PDF report
data/
  assemblies.json # Windows, mechanical, solar, climate, rates, regions, snow
  ontario_locations.json # 227 Ontario locations (snow loads, regions)
api/
  main.py         # FastAPI service wrapping engine/ for the web frontend
web/              # Next.js frontend (form, results dashboard, site-plan viewer)
ui/
  app.py          # Legacy Streamlit interface (reference during migration)
docs/
  METHODOLOGY.md    # Full calculation methodology, incl. site-planning heuristics
  generate_pdf.py   # METHODOLOGY.md -> EnerZen_Methodology.pdf
tests/
  test_site.py    # Unit tests for the site placement engine
```
