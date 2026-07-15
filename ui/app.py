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
from engine.report import generate_results_pdf

st.set_page_config(page_title="EnerZen — Building Performance", page_icon="◼", layout="wide",
                   initial_sidebar_state="expanded")

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

CHART_INK = "#18211D"
CHART_MUTED = "#66706A"
CHART_LINE = "#D9DDD8"


def chart_style(chart):
    """Apply the same typography and neutral colors to every Altair chart."""
    return (chart.configure(background="transparent")
            .configure_view(stroke=None)
            .configure_axis(labelColor=CHART_MUTED, titleColor=CHART_MUTED,
                            domainColor=CHART_LINE, tickColor=CHART_LINE,
                            gridColor=CHART_LINE, labelFont="Segoe UI",
                            titleFont="Segoe UI", titleFontWeight=600)
            .configure_legend(labelColor=CHART_MUTED, titleColor=CHART_MUTED,
                              labelFont="Segoe UI", titleFont="Segoe UI")
            .configure_text(font="Segoe UI", color=CHART_INK))

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
    :root {
        --ink: #18211d;
        --muted: #66706a;
        --paper: #f5f4ef;
        --surface: #fffefa;
        --line: #d9ddd8;
        --forest: #214e3b;
        --forest-dark: #17382b;
        --sage: #dfe9df;
        --selected: #d8e6dc;
        --selected-hover: #c9dccc;
        --hover: #edf2ed;
        --control-border: #aeb7b0;
        --focus: #f1c453;
        --disabled: #eceeea;
        --disabled-text: #707873;
        --success-bg: #e5eee5;
        --warning-bg: #f4eadb;
        --error-bg: #f2e2df;
        --amber: #7b4d18;
        --red: #9f3f35;
    }
    html, body, [class*="css"], button, input, select, textarea {
        font-family: Aptos, "Segoe UI Variable", "Segoe UI", Arial, sans-serif !important;
    }
    .stApp { background: var(--paper); color: var(--ink); }
    .block-container { padding: 2.1rem 2.5rem 5rem; max-width: 1180px; }
    header[data-testid="stHeader"] { background: transparent; }
    #MainMenu, footer { visibility: hidden; }
    h1, h2, h3, h4, h5, h6 { font-family: Aptos, "Segoe UI Variable", "Segoe UI", Arial,
                              sans-serif !important; color:var(--ink) !important;
                              letter-spacing:-.025em; font-weight:720 !important; }
    h3 { font-size: 1.7rem !important; margin-top: 2.2rem !important; }
    h4 { margin-top: 1.5rem !important; color: var(--ink) !important; }
    p, label, .stCaption { color: var(--muted); }
    .brand-row { display:flex; align-items:center; justify-content:space-between;
                 border-bottom:1px solid var(--line); padding-bottom:1rem; margin-bottom:2.8rem; }
    .wordmark { font-size:1rem; font-weight:750; letter-spacing:.12em; color:var(--forest); }
    .edition { font-size:.72rem; letter-spacing:.1em; text-transform:uppercase; color:var(--muted); }
    .eyebrow { color:var(--forest); font-size:.72rem; font-weight:750; letter-spacing:.14em;
               text-transform:uppercase; margin-bottom:.65rem; }
    .hero-title { font-family:Aptos, "Segoe UI Variable", "Segoe UI", Arial, sans-serif;
                  font-size:3.05rem; line-height:1.04; font-weight:730; letter-spacing:-.045em;
                  max-width:760px; color:var(--ink); margin:0 0 .9rem; }
    .hero-copy { font-size:1.03rem; line-height:1.6; max-width:690px; color:var(--muted);
                 margin-bottom:2rem; }
    .section-kicker { margin:2.8rem 0 .1rem; color:var(--forest); font-size:.7rem;
                      font-weight:750; letter-spacing:.14em; text-transform:uppercase; }
    .result-intro { border-top:1px solid var(--line); border-bottom:1px solid var(--line);
                    padding:1.25rem 0; margin:1.2rem 0 1.6rem; color:var(--muted); }
    [data-testid="stSidebar"] { background:#e9ece6; border-right:1px solid var(--line); }
    [data-testid="stSidebar"] .block-container { padding:1.8rem 1.35rem 3rem; }
    [data-testid="stSidebar"] h2 { font-size:1.45rem !important; margin-bottom:.2rem; }
    [data-testid="stSidebar"] .stMarkdown p { margin-bottom:.35rem; }
    .side-step { color:var(--forest); font-size:.68rem; font-weight:800; letter-spacing:.12em;
                 text-transform:uppercase; border-top:1px solid var(--line); padding-top:1.15rem;
                 margin-top:1.15rem; }
    div[data-testid="stMetric"] { background:var(--surface); border:1px solid var(--line);
                                  border-radius:3px; padding:1rem 1.05rem; min-height:108px; }
    [data-testid="stMetricLabel"] { font-size:.72rem; font-weight:700; letter-spacing:.06em;
                                    text-transform:uppercase; color:var(--muted); }
    [data-testid="stMetricValue"] { font-family:Aptos, "Segoe UI Variable", "Segoe UI", Arial,
                                    sans-serif !important; font-size:1.7rem; font-weight:700;
                                    color:var(--ink); letter-spacing:-.025em; }
    .pill { display:inline-flex; align-items:center; border:1px solid currentColor;
            border-radius:2px; padding:5px 9px; font-size:.7rem; font-weight:750;
            letter-spacing:.04em; text-transform:uppercase; }
    .pill-pass { background:var(--success-bg); color:var(--forest); }
    .pill-warn { background:var(--warning-bg); color:var(--amber); }
    .pill-fail { background:var(--error-bg); color:var(--red); }
    .stButton > button { border-radius:2px; min-height:46px; font-weight:750; letter-spacing:.02em; }
    .stButton > button[kind="primary"] { background:var(--forest); border-color:var(--forest); }
    .stButton > button[kind="primary"]:hover { background:var(--forest-dark); border-color:var(--forest-dark); }
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background:var(--surface); border:1px solid var(--forest); color:var(--forest-dark);
        font-weight:800; box-shadow:none;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
        background:var(--hover); border-color:var(--forest-dark); color:var(--forest-dark);
    }
    .stButton > button:focus-visible, input:focus-visible, textarea:focus-visible,
    [tabindex="0"]:focus-visible { outline:3px solid var(--focus) !important;
                                  outline-offset:2px !important; box-shadow:none !important; }
    div[data-baseweb="select"] > div, div[data-testid="stNumberInput"] input,
    div[data-testid="stTextInput"] input { background:var(--surface); border:1px solid var(--control-border);
                                           border-radius:2px; color:var(--ink); }
    div[data-baseweb="select"] > div:hover { border-color:var(--forest); }
    div[data-baseweb="select"] [aria-selected="true"] { background:var(--selected) !important;
                                                            color:var(--forest-dark) !important; }
    [data-baseweb="popover"] { color:var(--ink); }
    [data-baseweb="popover"] ul { background:var(--surface) !important; border:1px solid var(--line); }
    [data-baseweb="popover"] [role="option"] { color:var(--ink) !important; }
    [data-baseweb="popover"] [role="option"]:hover { background:var(--hover) !important; }
    [data-baseweb="popover"] [role="option"][aria-selected="true"] {
        background:var(--selected) !important; color:var(--forest-dark) !important; font-weight:700;
    }
    div[role="radiogroup"] { gap:.35rem; flex-wrap:wrap; }
    div[role="radiogroup"] label { background:var(--surface); border:1px solid var(--control-border);
                                    border-radius:2px; padding:.38rem .55rem; margin:0; }
    div[role="radiogroup"] label:hover { background:var(--hover); border-color:var(--forest); }
    div[role="radiogroup"] label:has(input:checked) { background:var(--selected);
                                                     border-color:var(--forest); color:var(--forest-dark); }
    div[role="radiogroup"] label:has(input:checked) p { color:var(--forest-dark) !important;
                                                       font-weight:700; }
    label[data-baseweb="checkbox"]:hover p { color:var(--ink) !important; }
    [data-testid="stSlider"] [role="slider"] { box-shadow:0 0 0 1px var(--surface); }
    [data-testid="stSlider"] [role="slider"]:focus-visible { outline:3px solid var(--focus) !important; }
    input:disabled, button:disabled { background:var(--disabled) !important;
                                     color:var(--disabled-text) !important; }
    div[data-testid="stExpander"] { background:var(--surface); border:1px solid var(--line);
                                    border-radius:3px; margin:.6rem 0; }
    div[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:3px; }
    div[data-testid="stAlert"] { border-radius:2px; }
    hr { border-color:var(--line); }
    @media (max-width: 760px) {
        .block-container { padding:1.25rem 1rem 3rem; }
        .hero-title { font-size:2.35rem; }
        .brand-row { margin-bottom:1.8rem; }
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="brand-row"><div class="wordmark">ENERZEN</div>'
            '<div class="edition">Ontario · Performance study</div></div>',
            unsafe_allow_html=True)
st.markdown('<div class="eyebrow">Residential systems configurator</div>'
            '<div class="hero-title">Find the right building system.</div>'
            '<div class="hero-copy">Compare wall, roof, foundation and mechanical systems using '
            'location-specific snow, climate and regional cost assumptions. Every recommendation '
            'keeps the underlying quantities visible.</div>', unsafe_allow_html=True)

# ── Inputs (sidebar) ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Project brief")
    st.caption("Define the building once. The engine tests every feasible assembly combination.")

    st.markdown('<div class="side-step">01 · Building</div>', unsafe_allow_html=True)
    typology = st.radio("Building type", ["single_family", "townhouse", "murb"],
                        format_func=lambda x: {"single_family": "Detached", "townhouse": "Townhouse",
                                               "murb": "Multi-unit"}[x], horizontal=True)
    storeys = st.radio("Storeys", [1, 2, 3], index=1, horizontal=True)
    footprint_cols = st.columns(2)
    footprint_length = footprint_cols[0].number_input(
        "Footprint length (m)", 4.0, 50.0, 10.0, step=0.5)
    footprint_width = footprint_cols[1].number_input(
        "Footprint width (m)", 4.0, 50.0, 7.5, step=0.5)
    floor_area = footprint_length * footprint_width * storeys
    st.caption(f"Footprint {footprint_length:g} × {footprint_width:g} m = "
               f"{footprint_length * footprint_width:g} m² · "
               f"conditioned floor area {floor_area:g} m²")
    num_units = st.number_input("Number of units", 1, 50, 1)

    st.markdown('<div class="side-step">02 · Site</div>', unsafe_allow_html=True)
    location = st.selectbox("Location (Ontario)", LOCATION_NAMES,
                            index=LOCATION_NAMES.index("Toronto") if "Toronto" in LOCATION_NAMES else 0,
                            help="Sets climate zone, snow load, regional energy rates and soil.")
    resolved = resolve_location(location)
    st.caption(f"Zone {resolved.climate_zone} · ground snow Ss {resolved.ss:g} kPa · "
               f"roof load S {resolved.roof_snow_load_kpa:g} kPa · "
               f"{resolved.snow_tier['joist_depth_in']}\" preliminary joist · "
               f"{resolved.region_name}")
    if resolved.over_snow_range:
        st.warning("Ground snow Ss exceeds the two standard options — structural review required.")
    orientation = st.radio("Main facade faces", ["S", "E", "W", "N"], horizontal=True,
                           format_func=lambda x: {"S": "South", "N": "North",
                                                   "E": "East", "W": "West"}[x])
    wwr = st.slider("Window-to-wall ratio", 0.10, 0.45, 0.20, step=0.05)

    st.markdown('<div class="side-step">03 · Brief</div>', unsafe_allow_html=True)
    target_label = st.radio("Performance target", ["code", "nzr", "passive_house"],
                            index=1, format_func=lambda x: LABEL_NAMES[x])
    solar_option_id = st.selectbox("Solar (rooftop PV)",
                                   [s["id"] for s in CATALOG["solar"]],
                                   format_func=lambda x: SOLAR_LABELS[x])
    budget = st.number_input("Budget per unit (CAD $)", 200_000, 1_500_000,
                             500_000, step=25_000, format="%d")
    has_ac = st.checkbox("Include air conditioning", value=True,
                         help="Adds central AC when the heating plant is a furnace. "
                              "Heat pumps cool inherently — no extra cost.")
    allow_gas = st.checkbox("Allow natural gas systems", value=True,
                            help="Uncheck for an all-electric home (excludes gas furnaces).")

    with st.expander("Ranking priorities"):
        st.caption("How much each objective counts in the ranking.")
        w_cost   = st.slider("Cost",   0, 10, 3)
        w_speed  = st.slider("Speed",  0, 10, 2)
        w_carbon = st.slider("Carbon", 0, 10, 3)
        w_energy = st.slider("Energy", 0, 10, 2)

    run = st.button("Evaluate project", width="stretch", type="primary")

# ── Run + results ────────────────────────────────────────────────────────────
if not run:
    st.markdown('<div class="result-intro">Start with the project brief at left. '
                'The first study evaluates cost, speed, embodied carbon and energy together.</div>',
                unsafe_allow_html=True)
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
    has_ac=has_ac, allow_gas=allow_gas,
    footprint_length_m=float(footprint_length),
    footprint_width_m=float(footprint_width),
)

with st.spinner("Evaluating assembly combinations…"):
    results = optimize(spec, weights)

if not results:
    st.error("No configurations fit the budget and target. Try raising the budget "
             "or relaxing the target.")
    st.stop()

top = results[0]

# ── Headline ─────────────────────────────────────────────────────────────────
st.markdown('<div class="section-kicker">Recommendation 01</div>', unsafe_allow_html=True)
st.markdown("### Best-fit configuration")
st.markdown(f'<div class="result-intro">{location} · {footprint_length:g} × '
            f'{footprint_width:g} m footprint · {storeys} storey'
            f'{"s" if storeys > 1 else ""} · {floor_area:g} m² conditioned</div>',
            unsafe_allow_html=True)
nzr_p = top.nzr_probability
nzr_cls = "pill-pass" if nzr_p >= 0.8 else ("pill-warn" if nzr_p >= 0.5 else "pill-fail")
status = [f'<span class="pill {nzr_cls}">Net Zero Ready — {nzr_p:.0%} likely</span>']
if top.pv_capacity_kw > 0:
    status.append('<span class="pill pill-pass">✓ Net Zero</span>' if top.net_zero
                  else '<span class="pill pill-fail">Not net zero</span>')
st.markdown(" &nbsp; ".join(status), unsafe_allow_html=True)

report_labels = {
    "target": LABEL_NAMES[target_label],
    "wall": WALL_LABELS[top.wall_id] +
            (f" + {top.wall_ext_rigid_in:g}\" exterior rigid" if top.wall_ext_rigid_in else ""),
    "roof": ROOF_LABELS[top.roof_id] + f"; {top.joist_depth_in}\" joist" +
            (f" + {top.roof_deck_rigid_in:g}\" over-deck rigid"
             if top.roof_deck_rigid_in else ""),
    "floor": FLOOR_LABELS[top.floor_id] +
             (f"; {top.floor_rigid_in:g} mm EPS blanket" if top.floor_id == "FA1" else ""),
    "window": WINDOW_LABELS[top.window_id],
    "mechanical": MECH_LABELS[top.mechanical_id],
    "solar": SOLAR_LABELS[solar_option_id],
}
report_pdf = generate_results_pdf(spec, top, resolved, report_labels)
safe_location = "".join(ch if ch.isalnum() else "-" for ch in location).strip("-").lower()
st.download_button(
    "Download project report (PDF)", data=report_pdf,
    file_name=f"enerzen-{safe_location}-performance-report.pdf",
    mime="application/pdf", width="content",
    help="Professional summary of the project inputs, recommendation, quantities, costs and limitations.")

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
c[2].metric("30-yr lifecycle cost", f"${top.lifecycle_cost_30yr:,.0f}",
            help=f"Upfront (less solar rebate) + present value of energy bills. "
                 f"20-yr: ${top.lifecycle_cost_20yr:,.0f}")
c[3].metric("Solar", f"{top.pv_capacity_kw:g} kW ({top.pv_generation_kwh_yr:,.0f} kWh/yr)"
            if top.pv_capacity_kw else "None")

st.caption(f"EnerGuide estimate ~{top.energuide_score:g}/100  ·  "
           f"NZR threshold {top.energy.nzr_threshold:g} kWh/m²/yr for this climate zone.")

# ── The assembly ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-kicker">Specification</div>', unsafe_allow_html=True)
st.markdown("#### Selected building systems")
def _rigid(n): return f" + {n:g}\" exterior rigid" if n else ""
a = st.columns(2)
a[0].markdown(
    f"- **Wall** — {WALL_LABELS[top.wall_id]}{_rigid(top.wall_ext_rigid_in)}\n"
    f"- **Roof** — {ROOF_LABELS[top.roof_id]} ({top.joist_depth_in}\" joist)"
    f"{_rigid(top.roof_deck_rigid_in)}\n"
    f"- **Floor** — {FLOOR_LABELS[top.floor_id]}"
    + (f" ({top.floor_rigid_in:g} mm EPS under slab + 1.5 m beyond each edge)"
       if top.floor_id == "FA1" else " (grade-beam foundation)"))
a[1].markdown(
    f"- **Windows** — {WINDOW_LABELS[top.window_id]}\n"
    f"- **Mechanical** — {MECH_LABELS[top.mechanical_id]}\n"
    f"- **Solar** — {SOLAR_LABELS[solar_option_id]}")

if top.panel_schedule:
    ps = top.panel_schedule
    st.caption(f"Panels — {ps['wall_panels']} wall · {ps['roof_panels']} roof · "
               f"{ps['floor_panels']} floor · {ps['crane_lifts']} crane lifts")

if top.cost_breakdown:
    with st.expander("Cost breakdown (itemized)"):
        cb = top.cost_breakdown
        st.markdown("**Envelope materials by assembly**")
        for label, amount in cb["envelope_material_split"].items():
            st.markdown(f"- {label.replace('_', ' ').title()}: **${amount:,.0f}**")
        st.markdown(f"- Envelope installation labour: **${cb['labour_cost']:,.0f}** "
                    f"({cb['labour_hours']:g} hours)")
        st.markdown("**Whole-project lines**")
        lines = [("Envelope (materials + install)", cb["envelope_cost"]),
                 ("Panel connections & sealing", cb["connections_cost"]),
                 ("Interior partitions", cb["partitions_cost"]),
                 ("Exterior trim & finishes", cb["ext_finishes_cost"]),
                 ("Mechanical (sized to floor area)", cb["mechanical_cost"]),
                 ("Fit-out & services", cb["fitout_cost"]),
                 ("Contingency (8%)", cb["contingency_cost"])]
        for label, amount in lines:
            st.markdown(f"- {label}: **${amount:,.0f}**")
        st.markdown(f"- Construction total: **${cb['total_per_unit']:,.0f}** "
                    f"(${cb['cost_per_m2']:,.0f}/m²) — solar added separately")

if top.assembly_breakdown:
    with st.expander("R-value, quantities and foundation detail"):
        for key in ("wall", "roof", "floor"):
            detail = top.assembly_breakdown[key]
            nominal = detail.get("r_nominal")
            nominal_text = f"nominal R-{nominal}, " if nominal is not None else ""
            st.markdown(
                f"**{key.title()}** — {nominal_text}effective R-{detail['r_effective']}, "
                f"U {detail['u_value']} W/m²·K, materials ${detail['cost_m2']:,.2f}/m²")
            if "bridging_loss_pct" in detail:
                st.caption(f"Thermal-bridging loss: {detail['bridging_loss_pct']:g}%")
        floor_detail = top.assembly_breakdown["floor"]
        if "eps_area_m2" in floor_detail:
            st.markdown("**Slab-on-grade quantities**")
            st.markdown(
                f"- Footprint: {floor_detail['footprint_length_m']:g} × "
                f"{floor_detail['footprint_width_m']:g} m = "
                f"{floor_detail['footprint_area_m2']:g} m²\n"
                f"- EPS blanket: {floor_detail['extended_length_m']:g} × "
                f"{floor_detail['extended_width_m']:g} m = "
                f"{floor_detail['eps_area_m2']:g} m²; "
                f"{floor_detail['eps_volume_m3']:g} m³\n"
                f"- 100 mm slab concrete: {floor_detail['slab_concrete_m3']:g} m³\n"
                f"- Frost-wall concrete: {floor_detail['frost_wall_concrete_m3']:g} m³ "
                f"at {floor_detail['frost_depth_m']:g} m frost depth")
            fc = floor_detail["cost_split_total"]
            st.markdown(f"Slab concrete **${fc['slab']:,.0f}** · EPS **${fc['eps']:,.0f}** · "
                        f"frost wall **${fc['frost_wall']:,.0f}**")

# ── Alternatives ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-kicker">Shortlist</div>', unsafe_allow_html=True)
st.markdown("#### Other viable configurations")
st.caption(f"{len(results)} feasible configurations ranked by your priorities.")

rows = [{
    "Wall": WALL_LABELS[r.wall_id], "Roof": ROOF_LABELS[r.roof_id],
    "Windows": WINDOW_LABELS[r.window_id], "Mech": MECH_LABELS[r.mechanical_id],
    "Cost": f"${r.construction_cost:,.0f}", "Wks": f"{r.construction_weeks:.0f}",
    "Net EUI": f"{r.net_eui_kwh_m2_yr:g}", "Carbon": f"{r.embodied_carbon_kg_co2e_m2:.0f}",
    "Bill/mo": f"${r.avg_monthly_utility:,.0f}", "30yr LCC": f"${r.lifecycle_cost_30yr:,.0f}",
    "NZR likely": f"{r.nzr_probability:.0%}", "Net Zero": "✓" if r.net_zero else "·",
} for r in results[:20]]
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

# ── How EnerZen compares ─────────────────────────────────────────────────────
st.markdown('<div class="section-kicker">Performance</div>', unsafe_allow_html=True)
st.markdown("#### Energy profile")
st.caption("Envelope demand and whole-home energy intensity. Lower is better.")

intensity = st.columns(3)
intensity[0].metric(
    "TEDI", f"{top.energy.tedi_kwh_m2_yr:g} kWh/mÂ²/yr",
    delta=f"{top.energy.tedi_kwh_m2_yr - top.energy.nzr_threshold:+g} vs NZR limit",
    delta_color="inverse",
    help="Thermal Energy Demand Intensity: envelope heating demand before plant efficiency.")
intensity[1].metric(
    "MEUI", f"{top.energy.meui_kwh_m2_yr:g} kWh/mÂ²/yr",
    help="Mechanical Energy Use Intensity: purchased heating, cooling and hot-water energy.")
intensity[2].metric(
    "Total site EUI", f"{top.eui_kwh_m2_yr:g} kWh/mÂ²/yr",
    help="All purchased site energy before solar, including appliances and lighting.")
st.caption(f"This climate zone's Net Zero Ready TEDI threshold is "
           f"{top.energy.nzr_threshold:g} kWh/mÂ²/yr.")

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
        domain=["Benchmark", "EnerZen"], range=["#B8BDB7", "#214E3B"]), legend=None),
    tooltip=["label", "eui"],
)
labels = bars.mark_text(align="left", dx=4, color=CHART_MUTED).encode(
    text=alt.Text("eui:Q", format=".0f"))
st.altair_chart(chart_style((bars + labels).properties(height=180)), width="stretch")

pct = round((1 - top.eui_kwh_m2_yr / bench_eui["code_built_new"]) * 100)
st.caption(f"~{pct}% less energy than a new code-built home before solar. "
           "Benchmarks: NRCan residential intensity, CHBA Net Zero program. "
           "The EUI comparison and TEDI compliance test are intentionally kept separate.")

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
        domain=["Benchmark", "EnerZen"], range=["#B8BDB7", "#214E3B"]), legend=None),
    tooltip=["label", "ec"],
)
ec_labels = ec_bars.mark_text(align="left", dx=4, color=CHART_MUTED).encode(
    text=alt.Text("ec:Q", format=".0f"))
st.altair_chart(chart_style((ec_bars + ec_labels).properties(height=100)), width="stretch")
st.caption(f"Benchmark {bench_ec} kgCO₂e/m² — cradle-to-gate mean for new low-rise residential "
           "(Living Materials Lab, 2024).")

# ── Monthly utility bill ─────────────────────────────────────────────────────
st.markdown("#### Monthly operating cost")
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
        domain=["electricity", "gas"], range=["#214E3B", "#7B4D18"]),
        legend=alt.Legend(title=None, orient="top")),
    tooltip=["month", "Energy", "cost"],
).properties(height=240)
st.altair_chart(chart_style(util_chart), width="stretch")
st.caption(f"~${top.annual_utility_cost:,.0f}/yr total"
           + (" — PV net-metering credits offset summer electricity." if top.pv_capacity_kw else "")
           + " Rates: OEB electricity ~$0.16/kWh, Enbridge gas ~$0.055/kWh (2025).")

# ── Cost vs. energy trade-off ────────────────────────────────────────────────
st.markdown('<div class="section-kicker">Decision field</div>', unsafe_allow_html=True)
st.markdown("#### Cost and energy trade-off")
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
        range=["#567A61", "#214E3B", "#9F3F35"]), title=None),
    tooltip=["cost", "eui", "status"],
)
st.altair_chart(chart_style(pts.properties(height=320)), width="stretch")
