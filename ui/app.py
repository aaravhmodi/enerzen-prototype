"""
EnerZen Performance Engine — Streamlit UI
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import streamlit as st
import pandas as pd

from engine.optimizer import ProjectSpec, optimize

st.set_page_config(page_title="EnerZen Performance Engine", page_icon="🏠", layout="wide")

# ── Catalog for display labels ───────────────────────────────────────────────
with open(Path(__file__).parent.parent / "data" / "assemblies.json") as f:
    CATALOG = json.load(f)

WALL_LABELS   = {w["id"]: w["name"] for w in CATALOG["wall_panels"]}
ROOF_LABELS   = {r["id"]: r["name"] for r in CATALOG["roof_cassettes"]}
FLOOR_LABELS  = {f["id"]: f["name"] for f in CATALOG["floor_cassettes"]}
WINDOW_LABELS = {w["id"]: w["name"] for w in CATALOG["windows"]}
MECH_LABELS   = {m["id"]: m["name"] for m in CATALOG["mechanical"]}
SOLAR_LABELS  = {s["id"]: s["name"] for s in CATALOG["solar"]}

ZONE_LABELS = {
    "6":  "Zone 6 — Toronto / Southern ON",
    "7a": "Zone 7a — Ottawa / Eastern ON",
    "7b": "Zone 7b — Northern ON / Sudbury",
}
LABEL_NAMES = {
    "code": "Building Code baseline",
    "nzr": "Net Zero Ready",
    "passive_house": "Passive House-inspired",
}

st.markdown("""
<style>
    .block-container { padding-top: 2.5rem; max-width: 1100px; }
    h1 { font-size: 1.6rem !important; color: #1A5276; margin-bottom: 0.2rem; }
    .caption { color: #888; font-size: 0.9rem; margin-bottom: 1.5rem; }
    [data-testid="stMetricValue"] { font-size: 1.5rem; color: #1A5276; }
    .pill { display:inline-block; border-radius: 999px; padding: 3px 12px;
            font-size: 0.8rem; font-weight: 600; }
    .pill-pass { background:#D5F5E3; color:#1E8449; }
    .pill-fail { background:#FADBD8; color:#C0392B; }
</style>
""", unsafe_allow_html=True)

st.markdown("# EnerZen Performance Engine")
st.markdown('<div class="caption">Describe your project. Get the optimal assembly, costs, and performance.</div>',
            unsafe_allow_html=True)

# ── Inputs (sidebar) ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Your project")

    st.markdown("**The building**")
    typology = st.selectbox("Building type", ["single_family", "townhouse", "murb"],
                            format_func=lambda x: x.replace("_", " ").title())
    floor_area = st.number_input("Floor area (m²)", 80, 500, 150, step=10)
    storeys = st.selectbox("Storeys", [1, 2, 3], index=1)
    num_units = st.number_input("Number of units", 1, 50, 1)

    st.markdown("**The site**")
    climate_zone = st.selectbox("Climate zone", ["6", "7a", "7b"],
                                format_func=lambda z: ZONE_LABELS[z])
    orientation = st.selectbox("Main facade faces", ["S", "N", "E", "W"],
                               format_func=lambda x: {"S": "South", "N": "North",
                                                       "E": "East", "W": "West"}[x])
    wwr = st.slider("Window-to-wall ratio", 0.10, 0.45, 0.20, step=0.05)

    st.markdown("**The target**")
    target_label = st.selectbox("Performance target", ["code", "nzr", "passive_house"],
                                index=1, format_func=lambda x: LABEL_NAMES[x])
    solar_option_id = st.selectbox("Solar (rooftop PV)",
                                   [s["id"] for s in CATALOG["solar"]],
                                   format_func=lambda x: SOLAR_LABELS[x])
    budget = st.number_input("Budget per unit (CAD $)", 200_000, 1_500_000,
                             500_000, step=25_000, format="%d")

    with st.expander("Priorities (advanced)"):
        st.caption("How much each objective counts in the ranking.")
        w_cost   = st.slider("Cost",   0, 10, 3)
        w_speed  = st.slider("Speed",  0, 10, 2)
        w_carbon = st.slider("Carbon", 0, 10, 3)
        w_energy = st.slider("Energy", 0, 10, 2)

    run = st.button("Run engine", use_container_width=True, type="primary")

# ── Run + results ────────────────────────────────────────────────────────────
if not run:
    st.info("Set your project details in the sidebar, then **Run engine**.")
    st.stop()

total_w = w_cost + w_speed + w_carbon + w_energy
if total_w == 0:
    st.error("At least one priority must be greater than zero.")
    st.stop()

weights = {"cost": w_cost / total_w, "speed": w_speed / total_w,
           "carbon": w_carbon / total_w, "energy": w_energy / total_w}

spec = ProjectSpec(
    typology=typology, climate_zone=climate_zone, floor_area_m2=float(floor_area),
    storeys=storeys, orientation=orientation, window_to_wall_ratio=wwr,
    budget_per_unit=float(budget), target_label=target_label,
    solar_option_id=solar_option_id, num_units=num_units,
)

with st.spinner("Evaluating assembly combinations…"):
    results = optimize(spec, weights)

if not results:
    st.error("No configurations fit the budget and target. Try raising the budget "
             "or relaxing the target.")
    st.stop()

top = results[0]

# ── Headline ─────────────────────────────────────────────────────────────────
st.markdown("### Recommended configuration")
status = []
status.append('<span class="pill pill-pass">✓ Net Zero Ready</span>' if top.nzr_compliant
              else '<span class="pill pill-fail">Not NZR</span>')
if top.pv_capacity_kw > 0:
    status.append('<span class="pill pill-pass">✓ Net Zero</span>' if top.net_zero
                  else '<span class="pill pill-fail">Not net zero</span>')
st.markdown(" &nbsp; ".join(status), unsafe_allow_html=True)

c = st.columns(4)
c[0].metric("Cost / unit", f"${top.construction_cost:,.0f}")
c[1].metric("Build time", f"{top.construction_weeks:.0f} wks")
c[2].metric("Net energy use", f"{top.net_eui_kwh_m2_yr:g} kWh/m²/yr",
            help=f"Before solar: {top.eui_kwh_m2_yr:g}")
c[3].metric("EnerGuide", f"{top.energuide_score:g}/100")

c = st.columns(4)
c[0].metric("Embodied carbon", f"{top.embodied_carbon_kg_co2e_m2:.0f} kg/m²")
c[1].metric("Solar", f"{top.pv_capacity_kw:g} kW" if top.pv_capacity_kw else "None")
c[2].metric("PV generation", f"{top.pv_generation_kwh_yr:,.0f} kWh/yr")
c[3].metric("NZR threshold", f"{top.energy.nzr_threshold:g} kWh/m²/yr")

# ── The assembly ─────────────────────────────────────────────────────────────
st.markdown("#### Assembly")
a = st.columns(2)
a[0].markdown(
    f"- **Wall** — {WALL_LABELS[top.wall_id]}\n"
    f"- **Roof** — {ROOF_LABELS[top.roof_id]}\n"
    f"- **Floor** — {FLOOR_LABELS[top.floor_id]}")
a[1].markdown(
    f"- **Windows** — {WINDOW_LABELS[top.window_id]}\n"
    f"- **Mechanical** — {MECH_LABELS[top.mechanical_id]}\n"
    f"- **Solar** — {SOLAR_LABELS[solar_option_id]}")

if top.panel_schedule:
    ps = top.panel_schedule
    st.caption(f"Panels — {ps['wall_panels']} wall · {ps['roof_panels']} roof · "
               f"{ps['floor_panels']} floor · {ps['crane_lifts']} crane lifts")

# ── Alternatives ─────────────────────────────────────────────────────────────
st.markdown("#### Other options")
st.caption(f"{len(results)} feasible configurations ranked by your priorities.")

rows = [{
    "Wall": WALL_LABELS[r.wall_id], "Roof": ROOF_LABELS[r.roof_id],
    "Windows": WINDOW_LABELS[r.window_id], "Mech": MECH_LABELS[r.mechanical_id],
    "Cost": f"${r.construction_cost:,.0f}", "Wks": f"{r.construction_weeks:.0f}",
    "Net EUI": f"{r.net_eui_kwh_m2_yr:g}", "Carbon": f"{r.embodied_carbon_kg_co2e_m2:.0f}",
    "NZR": "✓" if r.nzr_compliant else "·", "Net Zero": "✓" if r.net_zero else "·",
} for r in results[:20]]
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.markdown("#### Cost vs. energy")
st.scatter_chart(
    pd.DataFrame({
        "Cost per unit ($)": [r.construction_cost for r in results[:20]],
        "Net EUI (kWh/m²/yr)": [r.net_eui_kwh_m2_yr for r in results[:20]],
        "Net Zero": [r.net_zero for r in results[:20]],
    }),
    x="Cost per unit ($)", y="Net EUI (kWh/m²/yr)", color="Net Zero",
    use_container_width=True,
)
