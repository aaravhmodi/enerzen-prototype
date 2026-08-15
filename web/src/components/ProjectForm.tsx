"use client";

import { useEffect, useState } from "react";
import { fetchCatalog, fetchLocations, runParseSpec, ProjectSpecInput, SiteSpecInput } from "@/lib/api";

export type FormState = {
  spec: ProjectSpecInput;
  site: SiteSpecInput;
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
  },
};

export default function ProjectForm({
  onSubmit,
  submitting,
}: {
  onSubmit: (state: FormState) => void;
  submitting: boolean;
}) {
  const [state, setState] = useState<FormState>(DEFAULT_STATE);
  const [locations, setLocations] = useState<string[]>([]);
  const [solarOptions, setSolarOptions] = useState<{ id: string; name: string }[]>([]);
  const [freeform, setFreeform] = useState("");
  const [parsing, setParsing] = useState(false);
  const [assumptions, setAssumptions] = useState<string[]>([]);
  const [parseError, setParseError] = useState<string | null>(null);

  useEffect(() => {
    fetchLocations().then(setLocations).catch(() => setLocations([]));
    fetchCatalog()
      .then((c) => setSolarOptions(c.solar))
      .catch(() => setSolarOptions([]));
  }, []);

  const updateSpec = <K extends keyof ProjectSpecInput>(key: K, value: ProjectSpecInput[K]) =>
    setState((s) => ({ ...s, spec: { ...s.spec, [key]: value } }));

  const updateSite = <K extends keyof SiteSpecInput>(key: K, value: SiteSpecInput[K]) =>
    setState((s) => ({ ...s, site: { ...s.site, [key]: value } }));

  async function handleParse() {
    if (!freeform.trim()) return;
    setParsing(true);
    setParseError(null);
    try {
      const parsed = await runParseSpec(freeform);
      setState((s) => ({
        spec: { ...s.spec, ...stripUndefined(parsed) },
        site: { ...s.site, ...stripUndefined(parsed) },
      }));
      setAssumptions(parsed.assumptions ?? []);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "Parsing failed");
    } finally {
      setParsing(false);
    }
  }

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(state);
      }}
    >
      <div className="rounded-xl border border-neutral-200 bg-white p-4">
        <label className="text-xs font-medium text-neutral-500">
          Describe the project (optional — AI will pre-fill the form)
        </label>
        <textarea
          className="mt-2 w-full rounded-md border border-neutral-300 p-2 text-sm"
          rows={3}
          placeholder="3-bed bungalow on a 50x120 ft lot in Ottawa, budget 450k, net-zero ready..."
          value={freeform}
          onChange={(e) => setFreeform(e.target.value)}
        />
        <button
          type="button"
          onClick={handleParse}
          disabled={parsing || !freeform.trim()}
          className="mt-2 rounded-md bg-neutral-800 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
        >
          {parsing ? "Parsing..." : "Fill form with AI"}
        </button>
        {parseError && <p className="mt-2 text-xs text-red-600">{parseError}</p>}
        {assumptions.length > 0 && (
          <ul className="mt-2 list-disc pl-4 text-xs text-neutral-500">
            {assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        )}
      </div>

      <fieldset className="rounded-xl border border-neutral-200 bg-white p-4">
        <legend className="px-1 text-xs font-semibold text-neutral-600">Building</legend>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Typology">
            <select
              className="input"
              value={state.spec.typology}
              onChange={(e) => updateSpec("typology", e.target.value)}
            >
              <option value="single_family">Single family</option>
              <option value="townhouse">Townhouse</option>
              <option value="murb">MURB</option>
            </select>
          </Field>
          <Field label="Storeys">
            <input type="number" className="input" min={1} value={state.spec.storeys}
              onChange={(e) => updateSpec("storeys", Number(e.target.value))} />
          </Field>
          <Field label="Floor area (m²)">
            <input type="number" className="input" value={state.spec.floor_area_m2}
              onChange={(e) => updateSpec("floor_area_m2", Number(e.target.value))} />
          </Field>
          <Field label="Footprint L × W (m)">
            <div className="flex gap-2">
              <input type="number" className="input" value={state.spec.footprint_length_m ?? ""}
                onChange={(e) => updateSpec("footprint_length_m", Number(e.target.value))} />
              <input type="number" className="input" value={state.spec.footprint_width_m ?? ""}
                onChange={(e) => updateSpec("footprint_width_m", Number(e.target.value))} />
            </div>
          </Field>
          <Field label="Location">
            <select className="input" value={state.spec.location ?? ""}
              onChange={(e) => updateSpec("location", e.target.value)}>
              {locations.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </Field>
          <Field label="Orientation (main facade)">
            <select className="input" value={state.spec.orientation}
              onChange={(e) => updateSpec("orientation", e.target.value as ProjectSpecInput["orientation"])}>
              <option value="N">North</option>
              <option value="S">South</option>
              <option value="E">East</option>
              <option value="W">West</option>
            </select>
          </Field>
          <Field label="Window-to-wall ratio">
            <input type="number" step={0.05} className="input" value={state.spec.window_to_wall_ratio}
              onChange={(e) => updateSpec("window_to_wall_ratio", Number(e.target.value))} />
          </Field>
          <Field label="Target">
            <select className="input" value={state.spec.target_label}
              onChange={(e) => updateSpec("target_label", e.target.value)}>
              <option value="code">Code minimum</option>
              <option value="nzr">Net Zero Ready</option>
              <option value="passive_house">Passive House</option>
            </select>
          </Field>
          <Field label="Solar (rooftop PV)">
            <select className="input" value={state.spec.solar_option_id}
              onChange={(e) => updateSpec("solar_option_id", e.target.value)}>
              {solarOptions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Budget per unit (CAD)">
            <input type="number" className="input" value={state.spec.budget_per_unit}
              onChange={(e) => updateSpec("budget_per_unit", Number(e.target.value))} />
          </Field>
        </div>
        <div className="mt-3 flex gap-4 text-xs text-neutral-600">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={state.spec.has_ac}
              onChange={(e) => updateSpec("has_ac", e.target.checked)} />
            Include air conditioning
          </label>
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={state.spec.allow_gas}
              onChange={(e) => updateSpec("allow_gas", e.target.checked)} />
            Allow natural gas systems
          </label>
        </div>
      </fieldset>

      <fieldset className="rounded-xl border border-neutral-200 bg-white p-4">
        <legend className="px-1 text-xs font-semibold text-neutral-600">Lot / site</legend>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Lot width (E-W, m)">
            <input type="number" className="input" value={state.site.lot_width_m}
              onChange={(e) => updateSite("lot_width_m", Number(e.target.value))} />
          </Field>
          <Field label="Lot depth (N-S, m)">
            <input type="number" className="input" value={state.site.lot_depth_m}
              onChange={(e) => updateSite("lot_depth_m", Number(e.target.value))} />
          </Field>
          <Field label="Street-facing side">
            <select className="input" value={state.site.street_side}
              onChange={(e) => updateSite("street_side", e.target.value as SiteSpecInput["street_side"])}>
              <option value="N">North</option>
              <option value="S">South</option>
              <option value="E">East</option>
              <option value="W">West</option>
            </select>
          </Field>
          <Field label="Front / side / rear setback (m)">
            <div className="flex gap-2">
              <input type="number" className="input" value={state.site.front_setback_m}
                onChange={(e) => updateSite("front_setback_m", Number(e.target.value))} />
              <input type="number" className="input" value={state.site.side_setback_m}
                onChange={(e) => updateSite("side_setback_m", Number(e.target.value))} />
              <input type="number" className="input" value={state.site.rear_setback_m}
                onChange={(e) => updateSite("rear_setback_m", Number(e.target.value))} />
            </div>
          </Field>
        </div>
      </fieldset>

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-lg bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
      >
        {submitting ? "Evaluating..." : "Evaluate project"}
      </button>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-xs">
      <span className="mb-1 block text-neutral-500">{label}</span>
      {children}
    </label>
  );
}

function stripUndefined<T extends object>(obj: T): Partial<T> {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null)) as Partial<T>;
}
