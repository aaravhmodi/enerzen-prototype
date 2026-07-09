"""
EnerZen Performance Engine — Streamlit prototype UI
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import json

from engine.optimizer import ProjectSpec, optimize
from engine.simulator import CLIMATE

st.set_page_config(
    page_title="EnerZen Performance Engine",
    page_icon="🏠",
    layout="wide",
)

# ── Catalog for display labels ──────────────────────────────────────────────
with open(Path(__file__).parent.parent / "data" / "assemblies.json") as f:
    CATALOG = json.load(f)

WALL_LABELS   = {w["id"]: w["name"] for w in CATALOG["wall_panels"]}
ROOF_LABELS   = {r["id"]: r["name"] for r in CATALOG["roof_cassettes"]}
FLOOR_LABELS  = {f["id"]: f["name"] for f in CATALOG["floor_cassettes"]}
WINDOW_LABELS = {w["id"]: w["name"] for w in CATALOG["windows"]}
MECH_LABELS   = {m["id"]: m["name"] for m in CATALOG["mechanical"]}

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-title { font-size: 2rem; font-weight: 700; color: #1A5276; margin-bottom: 0; }
    .sub-title  { font-size: 1rem; color: #666; margin-top: 0; margin-bottom: 2rem; }
    .metric-box { background: #EBF5FB; border-radius: 8px; padding: 1rem; text-align: center; }
    .metric-val { font-size: 1.6rem; font-weight: 700; color: #1A5276; }
    .metric-lbl { font-size: 0.8rem; color: #555; }
    .badge-pass { background: #D5F5E3; color: #1E8449; border-radius: 4px;
                  padding: 2px 8px; font-size: 0.8rem; font-weight: 600; }
    .badge-fail { background: #FADBD8; color: #C0392B; border-radius: 4px;
                  padding: 2px 8px; font-size: 0.8rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-title">EnerZen Performance Engine</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Enter your project. Get the optimal assembly configuration.</p>', unsafe_allow_html=True)

# ── Input form ───────────────────────────────────────────────────────────────
with st.form("project_form"):
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Project")
        typology = st.selectbox("Building type", ["single_family", "townhouse", "murb"],
                                format_func=lambda x: x.replace("_", " ").title())
        climate_zone = st.selectbox("Climate zone", ["6", "7a", "7b"],
                                    format_func=lambda z: f"Zone {z} — {CLIMATE[z]}" if False else {
                                        "6": "Zone 6 — Toronto / Southern ON",
                                        "7a": "Zone 7a — Ottawa / Eastern ON",
                                        "7b": "Zone 7b — Northern ON / Sudbury",
                                    }[z])
        floor_area = st.number_input("Conditioned floor area (m²)", 80, 500, 150, step=10)
        storeys = st.selectbox("Storeys", [1, 2, 3])
        num_units = st.number_input("Number of units", 1, 50, 1)

    with col2:
        st.subheader("Building")
        orientation = st.selectbox("Main facade orientation", ["S", "N", "E", "W"],
                                   format_func=lambda x: {"S": "South", "N": "North",
                                                           "E": "East",  "W": "West"}[x])
        wwr = st.slider("Window-to-wall ratio", 0.10, 0.45, 0.20, step=0.05,
                        help="Fraction of wall area that is glazing")
        budget = st.number_input("Budget ceiling per unit (CAD $)", 200_000, 1_500_000,
                                 500_000, step=25_000,
                                 format="%d")
        target_label = st.selectbox("Target performance label",
                                    ["code", "nzr", "passive_house"],
                                    index=1,
                                    format_func=lambda x: {
                                        "code": "Building Code baseline",
                                        "nzr": "CHBA Net Zero Ready",
                                        "passive_house": "Passive House-inspired",
                                    }[x])

    with col3:
        st.subheader("Priorities")
        st.caption("Adjust how much each objective is weighted in the ranking.")
        w_cost   = st.slider("Cost weight",   0, 10, 3)
        w_speed  = st.slider("Speed weight",  0, 10, 2)
        w_carbon = st.slider("Carbon weight", 0, 10, 3)
        w_energy = st.slider("Energy weight", 0, 10, 2)

    submitted = st.form_submit_button("Run Engine", use_container_width=True, type="primary")

# ── Run optimizer ─────────────────────────────────────────────────────────────
if submitted:
    total_w = w_cost + w_speed + w_carbon + w_energy
    if total_w == 0:
        st.error("At least one priority weight must be greater than zero.")
        st.stop()

    weights = {
        "cost":   w_cost   / total_w,
        "speed":  w_speed  / total_w,
        "carbon": w_carbon / total_w,
        "energy": w_energy / total_w,
    }

    spec = ProjectSpec(
        typology=typology,
        climate_zone=climate_zone,
        floor_area_m2=float(floor_area),
        storeys=storeys,
        orientation=orientation,
        window_to_wall_ratio=wwr,
        budget_per_unit=float(budget),
        target_label=target_label,
        num_units=num_units,
    )

    with st.spinner("Evaluating assembly combinations..."):
        results = optimize(spec, weights)

    if not results:
        st.error("No configurations found within the budget and performance constraints. "
                 "Try increasing the budget or relaxing the target label.")
        st.stop()

    st.success(f"Found **{len(results)}** feasible configurations. "
               f"Showing top results ranked by your priorities.")

    # ── Top recommendation ─────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Recommended Configuration")

    top = results[0]
    nzr_badge = '<span class="badge-pass">✓ NZR Compliant</span>' if top.nzr_compliant \
                else '<span class="badge-fail">✗ Not NZR</span>'

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Construction Cost", f"${top.construction_cost:,.0f}", help="Per unit")
    m2.metric("Build Time",  f"{top.construction_weeks:.1f} wks", help="Weeks to envelope close")
    m3.metric("EUI",  f"{top.eui_kwh_m2_yr} kWh/m²/yr")
    m4.metric("Embodied Carbon", f"{top.embodied_carbon_kg_co2e_m2} kgCO₂e/m²")
    m5.metric("EnerGuide", f"{top.energuide_score}/100")

    st.markdown(f"**NZR Status:** {nzr_badge} &nbsp;&nbsp; (threshold: {top.energy.nzr_threshold} kWh/m²/yr)",
                unsafe_allow_html=True)

    st.markdown("**Assembly:**")
    asm_col1, asm_col2 = st.columns(2)
    with asm_col1:
        st.write(f"- **Wall:** {WALL_LABELS[top.wall_id]}")
        st.write(f"- **Roof:** {ROOF_LABELS[top.roof_id]}")
        st.write(f"- **Floor:** {FLOOR_LABELS[top.floor_id]}")
    with asm_col2:
        st.write(f"- **Windows:** {WINDOW_LABELS[top.window_id]}")
        st.write(f"- **Mechanical:** {MECH_LABELS[top.mechanical_id]}")

    if top.panel_schedule:
        ps = top.panel_schedule
        st.markdown("**Panel Schedule:**")
        st.write(f"- Wall panels: {ps['wall_panels']} &nbsp;|&nbsp; "
                 f"Roof cassettes: {ps['roof_panels']} &nbsp;|&nbsp; "
                 f"Floor cassettes: {ps['floor_panels']} &nbsp;|&nbsp; "
                 f"Total crane lifts: {ps['crane_lifts']}")

    # ── All results table ──────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("All Feasible Configurations")

    rows = []
    for r in results[:30]:  # cap display at 30
        rows.append({
            "Rank": r.pareto_rank,
            "Wall":       WALL_LABELS[r.wall_id],
            "Roof":       ROOF_LABELS[r.roof_id],
            "Floor":      FLOOR_LABELS[r.floor_id],
            "Windows":    WINDOW_LABELS[r.window_id],
            "Mechanical": MECH_LABELS[r.mechanical_id],
            "Cost/unit":  f"${r.construction_cost:,.0f}",
            "Weeks":      f"{r.construction_weeks:.1f}",
            "EUI":        f"{r.eui_kwh_m2_yr}",
            "Carbon":     f"{r.embodied_carbon_kg_co2e_m2}",
            "NZR":        "✓" if r.nzr_compliant else "✗",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Trade-off chart ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Cost vs. Energy Trade-off")
    chart_data = pd.DataFrame({
        "Cost per unit ($)":    [r.construction_cost for r in results[:30]],
        "EUI (kWh/m²/yr)":     [r.eui_kwh_m2_yr for r in results[:30]],
        "NZR Compliant":        [r.nzr_compliant for r in results[:30]],
    })
    st.scatter_chart(chart_data, x="Cost per unit ($)", y="EUI (kWh/m²/yr)",
                     color="NZR Compliant", use_container_width=True)

else:
    st.info("Fill in the project details above and click **Run Engine** to see results.")
