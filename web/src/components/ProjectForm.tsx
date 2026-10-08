"use client";

import { useEffect, useState } from "react";
import {
  fetchArchetypes,
  fetchCatalog,
  fetchLocations,
  runParseSpec,
  ArchetypeInfo,
  OptimizationWeights,
  ProjectSpecInput,
  SiteSpecInput,
} from "@/lib/api";
import LocationInfoPanel from "@/components/LocationInfoPanel";
import WizardChrome, { WizardStep } from "@/components/WizardChrome";

export type FormState = {
  spec: ProjectSpecInput;
  site: SiteSpecInput;
  weights: OptimizationWeights;
};

const DEFAULT_STATE: FormState = {
  spec: {
    typology: "single_family",
    climate_zone: "6",
    floor_area_m2: 150,
    storeys: 2,
    orientation: "S",
    window_to_wall_ratio: 0.2,
    budget_per_unit: 500000,
    target_label: "nzr",
    solar_option_id: "PV0",
    mechanical_option_id: null,
    location: "Toronto",
    num_units: 1,
    has_ac: true,
    allow_gas: true,
    footprint_length_m: 12,
    footprint_width_m: 8,
  },
  site: {
    lot_width_m: 20,
    lot_depth_m: 30,
    street_side: "N",
    front_setback_m: 6,
    side_setback_m: 1.2,
    rear_setback_m: 7.5,
    latitude: null,
    longitude: null,
  },
  weights: { cost: 25, speed: 25, carbon: 25, energy: 25 },
};

const STEPS: WizardStep[] = [
  { label: "Brief", caption: "Project inputs" },
  { label: "Site", caption: "Planning context" },
  { label: "Design", caption: "Catalog selection" },
  { label: "Systems", caption: "Performance setup" },
  { label: "Priorities", caption: "Review + rank" },
];

export default function ProjectForm({
  onSubmit,
  submitting,
}: {
  onSubmit: (state: FormState) => void;
  submitting: boolean;
}) {
  const [state, setState] = useState<FormState>(DEFAULT_STATE);
  const [step, setStep] = useState(0);
  const [locations, setLocations] = useState<string[]>([]);
  const [solarOptions, setSolarOptions] = useState<{ id: string; name: string }[]>([]);
  const [mechanicalOptions, setMechanicalOptions] = useState<{ id: string; name: string; type: string }[]>([]);
  const [archetypes, setArchetypes] = useState<ArchetypeInfo[]>([]);
  const [selectedDesign, setSelectedDesign] = useState("");
  const [showAiAssist, setShowAiAssist] = useState(false);
  const [freeform, setFreeform] = useState("");
  const [parsing, setParsing] = useState(false);
  const [assumptions, setAssumptions] = useState<string[]>([]);
  const [parseError, setParseError] = useState<string | null>(null);

  useEffect(() => {
    fetchLocations().then(setLocations).catch(() => setLocations([]));
    fetchCatalog().then((catalog) => {
      setSolarOptions(catalog.solar);
      setMechanicalOptions(catalog.mechanical);
    }).catch(() => setSolarOptions([]));
    fetchArchetypes().then(setArchetypes).catch(() => setArchetypes([]));
  }, []);

  const updateSpec = <K extends keyof ProjectSpecInput>(key: K, value: ProjectSpecInput[K]) =>
    setState((current) => ({ ...current, spec: { ...current.spec, [key]: value } }));
  const updateSite = <K extends keyof SiteSpecInput>(key: K, value: SiteSpecInput[K]) =>
    setState((current) => ({ ...current, site: { ...current.site, [key]: value } }));
  const updateWeight = (key: keyof OptimizationWeights, value: number) =>
    setState((current) => ({ ...current, weights: { ...current.weights, [key]: value } }));

  function applyDesign(id: string) {
    setSelectedDesign(id);
    const design = archetypes.find((candidate) => candidate.id === id);
    if (!design) return;
    setState((current) => ({
      ...current,
      spec: {
        ...current.spec,
        typology: design.typology,
        floor_area_m2: design.floor_area_m2,
        storeys: design.storeys,
        footprint_length_m: design.footprint_length_m,
        footprint_width_m: design.footprint_width_m,
      },
    }));
  }

  async function handleParse() {
    if (!freeform.trim()) return;
    setParsing(true);
    setParseError(null);
    try {
      const parsed = await runParseSpec(freeform);
      setState((current) => ({
        spec: { ...current.spec, ...stripUndefined(parsed) },
        site: { ...current.site, ...stripUndefined(parsed) },
        weights: current.weights,
      }));
      setAssumptions(parsed.assumptions ?? []);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "Parsing failed");
    } finally {
      setParsing(false);
    }
  }

  const canContinue = step === 0
    ? Boolean(state.spec.location) && state.spec.floor_area_m2 > 0 && state.spec.storeys > 0
    : step === 1
      ? state.site.lot_width_m > 0 && state.site.lot_depth_m > 0
      : step === 3
        ? state.spec.budget_per_unit > 0
        : true;

  return (
    <form onSubmit={(event) => { event.preventDefault(); onSubmit(state); }}>
      <WizardChrome
        steps={STEPS}
        currentStep={step}
        eyebrow="Path A · Individual unit"
        title={STEPS[step].label}
        description={
          step === 0
            ? "Describe the home and its context before EnerZen evaluates any design direction."
            : step === 1
              ? "Give the engine a real parcel context so site fit and planning assumptions are visible early."
              : step === 2
                ? "Start from a catalog archetype or keep the brief custom and shape the geometry yourself."
                : step === 3
                  ? "Configure the envelope, mechanical strategy, renewables, and performance target."
                  : "Set the trade-offs EnerZen should use when it ranks feasible configurations."
        }
        onBack={() => setStep((current) => Math.max(0, current - 1))}
        onNext={() => setStep((current) => Math.min(STEPS.length - 1, current + 1))}
        nextDisabled={!canContinue}
        nextLabel={step === STEPS.length - 2 ? "Set priorities" : "Continue"}
        isLastStep={step === STEPS.length - 1}
        submitting={submitting}
        submitLabel="Evaluate individual unit"
      >
        {step === 0 && (
          <div className="space-y-5">
            <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-lime-50/80 p-4">
              <button type="button" onClick={() => setShowAiAssist((value) => !value)} className="flex w-full items-center justify-between text-left">
                <span><span className="text-xs font-semibold text-emerald-900">✨ AI-assisted brief</span><span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-emerald-700">Optional</span></span>
                <span className="text-[10px] font-semibold text-emerald-700">{showAiAssist ? "Hide" : "Describe project"}</span>
              </button>
              {showAiAssist && <div className="mt-3"><textarea className="input min-h-24 resize-none" rows={3} placeholder="3-bed home on a 50×120 ft lot in Toronto, budget 450k, net-zero ready…" value={freeform} onChange={(event) => setFreeform(event.target.value)} /><button type="button" onClick={handleParse} disabled={parsing || !freeform.trim()} className="mt-3 rounded-lg bg-stone-950 px-4 py-2 text-xs font-semibold text-white transition hover:bg-stone-800 disabled:opacity-40">{parsing ? "Parsing…" : "Fill brief with AI"}</button>{parseError && <p className="mt-2 text-xs text-red-600">{parseError}</p>}{assumptions.length > 0 && <ul className="mt-3 list-disc rounded-lg bg-white/80 py-2 pl-6 pr-3 text-xs text-emerald-900">{assumptions.map((assumption, index) => <li key={index}>{assumption}</li>)}</ul>}</div>}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Location"><select className="input" value={state.spec.location ?? ""} onChange={(event) => updateSpec("location", event.target.value)}>{locations.map((location) => <option key={location} value={location}>{location}</option>)}{!locations.includes(state.spec.location ?? "") && <option value={state.spec.location ?? ""}>{state.spec.location}</option>}</select></Field>
              <Field label="Typology"><select className="input" value={state.spec.typology} onChange={(event) => updateSpec("typology", event.target.value)}><option value="single_family">Single family</option><option value="townhouse">Townhouse</option><option value="murb">MURB</option></select></Field>
              <Field label="Storeys"><input type="number" className="input" min={1} value={state.spec.storeys} onChange={(event) => updateSpec("storeys", Number(event.target.value))} /></Field>
              <Field label="Floor area (m²)"><input type="number" className="input" min={1} value={state.spec.floor_area_m2} onChange={(event) => updateSpec("floor_area_m2", Number(event.target.value))} /></Field>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-5">
            <LocationInfoPanel location={state.spec.location} latitude={state.site.latitude} longitude={state.site.longitude} />
            <div className="grid gap-4 sm:grid-cols-2"><Field label="Lot width (E–W, m)"><input type="number" className="input" min={5} value={state.site.lot_width_m} onChange={(event) => updateSite("lot_width_m", Number(event.target.value))} /></Field><Field label="Lot depth (N–S, m)"><input type="number" className="input" min={5} value={state.site.lot_depth_m} onChange={(event) => updateSite("lot_depth_m", Number(event.target.value))} /></Field></div>
            <div><p className="text-xs font-medium text-stone-600">Street-facing side</p><div className="mt-2 grid grid-cols-4 gap-2">{(["N", "S", "E", "W"] as const).map((direction) => <button key={direction} type="button" onClick={() => updateSite("street_side", direction)} className={`rounded-xl border py-3 text-xs font-semibold transition ${state.site.street_side === direction ? "border-emerald-500 bg-emerald-50 text-emerald-800 shadow-sm" : "border-stone-200 bg-white text-stone-600 hover:border-emerald-300"}`}>{direction}</button>)}</div></div>
            <div className="grid gap-3 sm:grid-cols-3">{(["front_setback_m", "side_setback_m", "rear_setback_m"] as const).map((key) => <Field key={key} label={`${key.replace("_setback_m", "")} setback (m)`}><input type="number" className="input" min={0} step={0.1} value={state.site[key]} onChange={(event) => updateSite(key, Number(event.target.value))} /></Field>)}</div>
            <div className="grid gap-3 sm:grid-cols-2"><Field label="Latitude (optional)"><input type="number" className="input" step="any" value={state.site.latitude ?? ""} onChange={(event) => updateSite("latitude", event.target.value ? Number(event.target.value) : null)} /></Field><Field label="Longitude (optional)"><input type="number" className="input" step="any" value={state.site.longitude ?? ""} onChange={(event) => updateSite("longitude", event.target.value ? Number(event.target.value) : null)} /></Field></div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <button type="button" onClick={() => setSelectedDesign("")} className={`rounded-2xl border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md ${!selectedDesign ? "border-emerald-400 bg-gradient-to-br from-emerald-50 to-lime-50 shadow-sm" : "border-stone-200 bg-white"}`}><p className="text-sm font-semibold text-stone-900">Custom brief</p><p className="mt-1 text-[10px] leading-4 text-stone-500">Keep your project inputs and shape the form manually.</p></button>
              {archetypes.map((design) => <button type="button" key={design.id} onClick={() => applyDesign(design.id)} className={`rounded-2xl border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md ${selectedDesign === design.id ? "border-emerald-400 bg-gradient-to-br from-emerald-50 to-lime-50 shadow-sm" : "border-stone-200 bg-white"}`}><div className="flex items-start justify-between gap-3"><p className="text-sm font-semibold text-stone-900">{design.name}</p>{selectedDesign === design.id && <span className="text-xs text-emerald-700">Selected</span>}</div><p className="mt-1 text-[10px] leading-4 text-stone-500">{design.floor_area_m2} m² · {design.storeys} storey{design.storeys === 1 ? "" : "s"}</p><div className="mt-4 h-1 rounded-full bg-gradient-to-r from-emerald-500 to-lime-400 opacity-70" /></button>)}
            </div>
            <div className="grid gap-4 sm:grid-cols-2"><Field label="Orientation"><select className="input" value={state.spec.orientation} onChange={(event) => updateSpec("orientation", event.target.value as ProjectSpecInput["orientation"])}><option value="N">North</option><option value="S">South</option><option value="E">East</option><option value="W">West</option></select></Field><Field label="Footprint length × width (m)"><div className="flex gap-2"><input type="number" className="input" value={state.spec.footprint_length_m ?? ""} onChange={(event) => updateSpec("footprint_length_m", Number(event.target.value))} /><input type="number" className="input" value={state.spec.footprint_width_m ?? ""} onChange={(event) => updateSpec("footprint_width_m", Number(event.target.value))} /></div></Field></div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2"><Field label="Energy target"><select className="input" value={state.spec.target_label} onChange={(event) => updateSpec("target_label", event.target.value)}><option value="code">Code minimum</option><option value="nzr">Net Zero Ready</option><option value="passive_house">Passive House</option></select></Field><Field label="Budget per unit (CAD)"><input type="number" className="input" min={1} value={state.spec.budget_per_unit} onChange={(event) => updateSpec("budget_per_unit", Number(event.target.value))} /></Field><Field label="Window-to-wall ratio"><input type="number" className="input" step={0.05} min={0} max={1} value={state.spec.window_to_wall_ratio} onChange={(event) => updateSpec("window_to_wall_ratio", Number(event.target.value))} /></Field><Field label="Solar option"><select className="input" value={state.spec.solar_option_id} onChange={(event) => updateSpec("solar_option_id", event.target.value)}>{solarOptions.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}</select></Field><Field label="Mechanical strategy"><select className="input" value={state.spec.mechanical_option_id ?? ""} onChange={(event) => updateSpec("mechanical_option_id", event.target.value || null)}><option value="">Optimize across catalog</option>{mechanicalOptions.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}</select></Field></div>
            <div className="grid gap-3 sm:grid-cols-2"><Toggle label="Include air conditioning" checked={state.spec.has_ac} onChange={(value) => updateSpec("has_ac", value)} /><Toggle label="Allow natural gas systems" checked={state.spec.allow_gas} onChange={(value) => updateSpec("allow_gas", value)} /></div>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-5">
            <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-lime-50 p-5"><p className="eyebrow">Ready for evaluation</p><h3 className="mt-2 text-xl font-semibold tracking-tight text-stone-950">A brief the engine can explain.</h3><p className="mt-2 text-sm leading-6 text-stone-600">EnerZen will test feasible configurations, apply the performance gate, rank the trade-offs, and return the recommended unit.</p></div>
            <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm"><p className="text-xs font-semibold text-stone-800">Decision priorities</p><p className="mt-1 text-[10px] leading-4 text-stone-400">Adjust the trade-offs used to rank configurations that pass the performance gate.</p><div className="mt-4 grid gap-4 sm:grid-cols-2">{([["cost", "Capital cost"], ["energy", "Operating energy"], ["speed", "Construction speed"], ["carbon", "Embodied carbon"]] as const).map(([key, label]) => <label key={key} className="block text-xs"><span className="mb-1 flex items-center justify-between font-medium text-stone-600"><span>{label}</span><span className="font-semibold text-emerald-700">{state.weights[key]}%</span></span><input className="w-full accent-emerald-700" type="range" min={0} max={100} step={5} value={state.weights[key]} onChange={(event) => updateWeight(key, Number(event.target.value))} /></label>)}</div></div>
            <div className="grid gap-3 sm:grid-cols-2"><Summary label="Project" value={`${state.spec.typology.replace("_", " ")} · ${state.spec.floor_area_m2} m²`} /><Summary label="Site" value={`${state.site.lot_width_m} × ${state.site.lot_depth_m} m · ${state.spec.location}`} /><Summary label="Target" value={state.spec.target_label === "nzr" ? "Net Zero Ready" : state.spec.target_label === "passive_house" ? "Passive House" : "Code minimum"} /><Summary label="Priorities" value={`${state.weights.cost}% cost · ${state.weights.energy}% energy`} /></div>
            <div className="rounded-xl border border-stone-200 bg-stone-50/70 px-4 py-3 text-xs leading-5 text-stone-500">The engine will return ranked options and a site-fit view. Nothing is submitted until you press Evaluate individual unit.</div>
          </div>
        )}
      </WizardChrome>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block text-xs"><span className="mb-1.5 block font-medium text-stone-500">{label}</span>{children}</label>;
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="flex items-center justify-between gap-3 rounded-xl border border-stone-200 bg-stone-50/70 px-4 py-3 text-xs text-stone-600"><span>{label}</span><input className="h-4 w-4 accent-emerald-700" type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /></label>;
}

function Summary({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-stone-200 bg-white px-4 py-3"><p className="tile-label">{label}</p><p className="mt-1 text-sm font-semibold text-stone-900">{value}</p></div>;
}

function stripUndefined<T extends object>(object: T): Partial<T> {
  return Object.fromEntries(Object.entries(object).filter(([, value]) => value !== undefined && value !== null)) as Partial<T>;
}
