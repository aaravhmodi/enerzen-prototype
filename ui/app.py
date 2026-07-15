"""
EnerZen Performance Engine — Streamlit UI
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import streamlit as st
import pandas as pd
import altair as alt

from engine.optimizer import ProjectSpec, optimize
from engine.location import resolve as resolve_location, location_names

st.set_page_config(page_title="EnerZen Performance Engine", page_icon="🏠", layout="wide")

# ── Catalog for display labels ───────────────────────────────────────────────
with open(Path(__file__).parent.parent / "data" / "assemblies.json") as f:
    CATALOG = json.load(f)

from engine.assemblies import WALLS, ROOFS, FLOORS

WALL_LABELS   = {w.id: w.name for w in WALLS}
ROOF_LABELS   = {r.id: r.name for r in ROOFS}
FLOOR_LABELS  = {f.id: f.name for f in FLOORS}
WINDOW_LABELS = {w["id"]: w["name"] for w in CATALOG["windows"]}
MECH_LABELS   = {m["id"]: m["name"] for m in CATALOG["mechanical"]}
SOLAR_LABELS  = {s["id"]: s["name"] for s in CATALOG["solar"]}
BENCH = CATALOG["benchmarks"]
LOCATION_NAMES = location_names()

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
    .pill-warn { background:#FCF3CF; color:#B7950B; }
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
    location = st.selectbox("Location (Ontario)", LOCATION_NAMES,
                            index=LOCATION_NAMES.index("Toronto") if "Toronto" in LOCATION_NAMES else 0,
                            help="Sets climate zone, snow load, regional energy rates and soil.")
    resolved = resolve_location(location)
    st.caption(f"Zone {resolved.climate_zone} · snow {resolved.roof_snow_load_kpa} kPa "
               f"({resolved.snow_tier['joist_depth_in']}\" joist) · {resolved.region_name}")
    if resolved.over_snow_range:
        st.warning("Snow load exceeds the standard catalog — needs structural review.")
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
    typology=typology, climate_zone=resolved.climate_zone, floor_area_m2=float(floor_area),
    storeys=storeys, orientation=orientation, window_to_wall_ratio=wwr,
    budget_per_unit=float(budget), target_label=target_label,
    solar_option_id=solar_option_id, location=location, num_units=num_units,
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
nzr_p = top.nzr_probability
nzr_cls = "pill-pass" if nzr_p >= 0.8 else ("pill-warn" if nzr_p >= 0.5 else "pill-fail")
status = [f'<span class="pill {nzr_cls}">Net Zero Ready — {nzr_p:.0%} likely</span>']
if top.pv_capacity_kw > 0:
    status.append('<span class="pill pill-pass">✓ Net Zero</span>' if top.net_zero
                  else '<span class="pill pill-fail">Not net zero</span>')
st.markdown(" &nbsp; ".join(status), unsafe_allow_html=True)

c = st.columns(4)
c[0].metric("Cost / unit", f"${top.construction_cost:,.0f}")
c[1].metric("Build time", f"{top.construction_weeks:.0f} wks")
c[2].metric("Net energy use", f"{top.net_eui_kwh_m2_yr:g} kWh/m²/yr",
            help=f"Before solar: {top.eui_kwh_m2_yr:g}")
c[3].metric("Net Zero Ready", f"{top.nzr_probability:.0%}",
            help="Probability of meeting the NZR threshold across as-built variance "
                 "(airtightness, weather, occupancy, mechanical) — 400-run Monte Carlo. "
                 f"EnerGuide {top.energuide_score:g}/100.")

c = st.columns(4)
c[0].metric("Embodied carbon", f"{top.embodied_carbon_kg_co2e_m2:.0f} kg/m²")
c[1].metric("Utility bill", f"${top.avg_monthly_utility:,.0f}/mo",
            help=f"${top.annual_utility_cost:,.0f}/yr")
c[2].metric("60-yr lifecycle cost", f"${top.lifecycle_cost_60yr:,.0f}",
            help="Upfront (less solar rebate) + present value of energy bills")
c[3].metric("Solar", f"{top.pv_capacity_kw:g} kW ({top.pv_generation_kwh_yr:,.0f} kWh/yr)"
            if top.pv_capacity_kw else "None")

st.caption(f"EnerGuide estimate ~{top.energuide_score:g}/100  ·  "
           f"NZR threshold {top.energy.nzr_threshold:g} kWh/m²/yr for this climate zone.")

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
    "Bill/mo": f"${r.avg_monthly_utility:,.0f}", "60yr LCC": f"${r.lifecycle_cost_60yr:,.0f}",
    "NZR likely": f"{r.nzr_probability:.0%}", "Net Zero": "✓" if r.net_zero else "·",
} for r in results[:20]]
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── How EnerZen compares ─────────────────────────────────────────────────────
st.markdown("#### How this home compares")
st.caption("Energy use intensity vs. typical Ontario homes. Lower is better.")

bench_eui = BENCH["eui_kwh_m2_yr"]
compare = pd.DataFrame([
    {"label": "Typical existing home", "eui": bench_eui["existing_home"], "kind": "Benchmark"},
    {"label": "New home, built to code", "eui": bench_eui["code_built_new"], "kind": "Benchmark"},
    {"label": "EnerZen (envelope only)", "eui": top.eui_kwh_m2_yr, "kind": "EnerZen"},
])
if top.pv_capacity_kw > 0:
    compare = pd.concat([compare, pd.DataFrame([
        {"label": "EnerZen (after solar)", "eui": max(top.net_eui_kwh_m2_yr, 0), "kind": "EnerZen"},
    ])], ignore_index=True)

bars = alt.Chart(compare).mark_bar(cornerRadiusEnd=4).encode(
    x=alt.X("eui:Q", title="Energy use intensity (kWh/m²/yr)"),
    y=alt.Y("label:N", sort=None, title=None),
    color=alt.Color("kind:N", scale=alt.Scale(
        domain=["Benchmark", "EnerZen"], range=["#B0BEC5", "#1A5276"]), legend=None),
    tooltip=["label", "eui"],
)
labels = bars.mark_text(align="left", dx=4, color="#666").encode(text=alt.Text("eui:Q", format=".0f"))
nzr_rule = alt.Chart(pd.DataFrame({"x": [top.energy.nzr_threshold]})).mark_rule(
    color="#1E8449", strokeDash=[4, 4]).encode(x="x:Q")
st.altair_chart((bars + labels + nzr_rule).properties(height=180), use_container_width=True)

pct = round((1 - top.eui_kwh_m2_yr / bench_eui["code_built_new"]) * 100)
st.caption(f"~{pct}% less energy than a new code-built home "
           f"(green dashed line = Net Zero Ready threshold, {top.energy.nzr_threshold:g}). "
           "Benchmarks: NRCan residential intensity, CHBA Net Zero program.")

# Embodied carbon vs. benchmark
bench_ec = BENCH["embodied_carbon_kg_co2e_m2"]["conventional_new_build"]
ec = pd.DataFrame([
    {"label": "Conventional new build", "ec": bench_ec, "kind": "Benchmark"},
    {"label": "EnerZen (this config)", "ec": top.embodied_carbon_kg_co2e_m2, "kind": "EnerZen"},
])
ec_bars = alt.Chart(ec).mark_bar(cornerRadiusEnd=4).encode(
    x=alt.X("ec:Q", title="Embodied carbon (kgCO₂e/m²)"),
    y=alt.Y("label:N", sort=None, title=None),
    color=alt.Color("kind:N", scale=alt.Scale(
        domain=["Benchmark", "EnerZen"], range=["#B0BEC5", "#1A5276"]), legend=None),
    tooltip=["label", "ec"],
)
ec_labels = ec_bars.mark_text(align="left", dx=4, color="#666").encode(
    text=alt.Text("ec:Q", format=".0f"))
st.altair_chart((ec_bars + ec_labels).properties(height=100), use_container_width=True)
st.caption(f"Benchmark {bench_ec} kgCO₂e/m² — cradle-to-gate mean for new low-rise residential "
           "(Living Materials Lab, 2024).")

# ── Monthly utility bill ─────────────────────────────────────────────────────
st.markdown("#### Estimated monthly utility bill")
util = pd.DataFrame(top.utility["months"])
util_long = util.melt(id_vars="month", value_vars=["electricity", "gas"],
                      var_name="Energy", value_name="cost")
util_long["month"] = pd.Categorical(util_long["month"],
                                    categories=[m["month"] for m in top.utility["months"]],
                                    ordered=True)
util_chart = alt.Chart(util_long).mark_bar().encode(
    x=alt.X("month:N", sort=None, title=None),
    y=alt.Y("cost:Q", title="Cost ($)", stack="zero"),
    color=alt.Color("Energy:N", scale=alt.Scale(
        domain=["electricity", "gas"], range=["#1A5276", "#E67E22"]),
        legend=alt.Legend(title=None, orient="top")),
    tooltip=["month", "Energy", "cost"],
).properties(height=240)
st.altair_chart(util_chart, use_container_width=True)
st.caption(f"~${top.annual_utility_cost:,.0f}/yr total"
           + (" — PV net-metering credits offset summer electricity." if top.pv_capacity_kw else "")
           + " Rates: OEB electricity ~$0.16/kWh, Enbridge gas ~$0.055/kWh (2025).")

# ── Cost vs. energy trade-off ────────────────────────────────────────────────
st.markdown("#### Cost vs. energy across options")
opts = pd.DataFrame({
    "cost": [r.construction_cost for r in results[:20]],
    "eui": [r.net_eui_kwh_m2_yr for r in results[:20]],
    "status": ["Net Zero" if r.net_zero else ("NZR" if r.nzr_compliant else "Below NZR")
               for r in results[:20]],
})
pts = alt.Chart(opts).mark_circle(size=90, opacity=0.75).encode(
    x=alt.X("cost:Q", title="Cost per unit ($)", axis=alt.Axis(format="$,.0f")),
    y=alt.Y("eui:Q", title="Net EUI (kWh/m²/yr)"),
    color=alt.Color("status:N", scale=alt.Scale(
        domain=["Net Zero", "NZR", "Below NZR"],
        range=["#1E8449", "#1A5276", "#C0392B"]), title=None),
    tooltip=["cost", "eui", "status"],
)
thresh_rule = alt.Chart(pd.DataFrame({"y": [top.energy.nzr_threshold]})).mark_rule(
    color="#1E8449", strokeDash=[4, 4]).encode(y="y:Q")
st.altair_chart((pts + thresh_rule).properties(height=320), use_container_width=True)
