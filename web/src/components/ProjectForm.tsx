"use client";

import { useEffect, useState } from "react";
import { fetchCatalog, fetchLocations, runParseSpec, ProjectSpecInput, SiteSpecInput } from "@/lib/api";
import LocationInfoPanel from "@/components/LocationInfoPanel";

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
  const [showAiAssist, setShowAiAssist] = useState(false);
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
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(state);
      }}
    >
      <div className="section-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Project brief</p>
            <h2 className="mt-1 text-lg font-semibold text-stone-950">Build inputs</h2>
          </div>
        </div>
        <p className="mt-2 text-xs leading-5 text-stone-500">
          Fill in the fields below directly, or use the optional AI assist to pre-fill from a plain-English
          description.
        </p>

        {/* Optional AI assist — collapsed by default so it doesn't compete with the real inputs */}
        <div className="mt-4 rounded-xl border border-dashed border-emerald-300/70 bg-emerald-50/40">
          <button
            type="button"
            onClick={() => setShowAiAssist((v) => !v)}
            className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
          >
            <span className="flex items-center gap-2 text-xs font-semibold text-emerald-800">
              <span aria-hidden>✨</span> AI-assisted fill
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">
                Optional
              </span>
            </span>
            <span className="text-xs text-emerald-700">{showAiAssist ? "Hide ▾" : "Show ▸"}</span>
          </button>

          {showAiAssist && (
            <div className="border-t border-emerald-200/70 px-4 pb-4 pt-3">
              <label className="text-xs font-medium text-stone-500">
                Describe the project in a sentence or two and AI will pre-fill the fields below. You can review
                and edit every value afterwards.
              </label>
              <textarea
                className="input mt-2 min-h-24 resize-none"
                rows={3}
                placeholder="3-bed bungalow on a 50x120 ft lot in Ottawa, budget 450k, net-zero ready..."
                value={freeform}
                onChange={(e) => setFreeform(e.target.value)}
              />
              <button
                type="button"
                onClick={handleParse}
                disabled={parsing || !freeform.trim()}
                className="mt-3 rounded-lg bg-stone-950 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-stone-950/10 transition hover:-translate-y-0.5 hover:bg-stone-800 disabled:translate-y-0 disabled:opacity-40"
              >
                {parsing ? "Parsing..." : "Fill form with AI"}
              </button>
              {parseError && <p className="mt-2 text-xs text-red-600">{parseError}</p>}
              {assumptions.length > 0 && (
                <ul className="mt-3 list-disc rounded-lg border border-emerald-100 bg-emerald-50/70 py-2 pl-6 pr-3 text-xs text-emerald-900">
                  {assumptions.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>

      <fieldset className="section-card">
        <div className="section-heading">
          <span className="section-badge">1</span>
          <div>
            <legend className="text-sm font-semibold text-stone-800">Building</legend>
            <p className="text-xs text-stone-500">Required — describes what's being built and where.</p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <Field label="Typology" required>
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
          <Field label="Storeys" required>
            <input
              type="number"
              className="input"
              min={1}
              placeholder="e.g. 2"
              value={state.spec.storeys}
              onChange={(e) => updateSpec("storeys", Number(e.target.value))}
            />
          </Field>
          <Field label="Floor area (m²)" required hint="Total conditioned floor area, all storeys combined.">
            <input
              type="number"
              className="input"
              placeholder="e.g. 150"
              value={state.spec.floor_area_m2}
              onChange={(e) => updateSpec("floor_area_m2", Number(e.target.value))}
            />
          </Field>
          <Field
            label="Footprint L × W (m)"
            optional
            hint="Leave as-is to let the engine infer a reasonable footprint from floor area."
          >
            <div className="flex gap-2">
              <input
                type="number"
                className="input"
                placeholder="Length"
                value={state.spec.footprint_length_m ?? ""}
                onChange={(e) => updateSpec("footprint_length_m", Number(e.target.value))}
              />
              <input
                type="number"
                className="input"
                placeholder="Width"
                value={state.spec.footprint_width_m ?? ""}
                onChange={(e) => updateSpec("footprint_width_m", Number(e.target.value))}
              />
            </div>
          </Field>
          <Field label="Location" required hint="Sets the climate data used for energy simulation.">
            <select
              className="input"
              value={state.spec.location ?? ""}
              onChange={(e) => updateSpec("location", e.target.value)}
            >
              {locations.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Orientation" required hint="Direction the main glazing / front of the building faces.">
            <select
              className="input"
              value={state.spec.orientation}
              onChange={(e) => updateSpec("orientation", e.target.value as ProjectSpecInput["orientation"])}
            >
              <option value="N">North</option>
              <option value="S">South</option>
              <option value="E">East</option>
              <option value="W">West</option>
            </select>
          </Field>
        </div>

        <div className="mt-4">
          <LocationInfoPanel location={state.spec.location} />
        </div>
      </fieldset>

      <fieldset className="section-card">
        <div className="section-heading">
          <span className="section-badge">2</span>
          <div>
            <legend className="text-sm font-semibold text-stone-800">Performance & systems</legend>
            <p className="text-xs text-stone-500">Required — drives cost, energy, and carbon targets.</p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <Field label="Window-to-wall ratio" required hint="Glazed area as a fraction of total wall area (0–1).">
            <input
              type="number"
              step={0.05}
              min={0}
              max={1}
              className="input"
              placeholder="e.g. 0.2"
              value={state.spec.window_to_wall_ratio}
              onChange={(e) => updateSpec("window_to_wall_ratio", Number(e.target.value))}
            />
          </Field>
          <Field label="Energy target" required>
            <select
              className="input"
              value={state.spec.target_label}
              onChange={(e) => updateSpec("target_label", e.target.value)}
            >
              <option value="code">Code minimum</option>
              <option value="nzr">Net Zero Ready</option>
              <option value="passive_house">Passive House</option>
            </select>
          </Field>
          <Field label="Solar option" required>
            <select
              className="input"
              value={state.spec.solar_option_id}
              onChange={(e) => updateSpec("solar_option_id", e.target.value)}
            >
              {solarOptions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Budget per unit (CAD)" required>
            <input
              type="number"
              className="input"
              placeholder="e.g. 500000"
              value={state.spec.budget_per_unit}
              onChange={(e) => updateSpec("budget_per_unit", Number(e.target.value))}
            />
          </Field>
        </div>
        <div className="mt-4 grid gap-2 text-xs text-stone-600 sm:grid-cols-2">
          <label className="flex items-center justify-between gap-3 rounded-lg border border-stone-200 bg-stone-50/70 px-3 py-2">
            <span>Include air conditioning</span>
            <input
              className="h-4 w-4 accent-emerald-700"
              type="checkbox"
              checked={state.spec.has_ac}
              onChange={(e) => updateSpec("has_ac", e.target.checked)}
            />
          </label>
          <label className="flex items-center justify-between gap-3 rounded-lg border border-stone-200 bg-stone-50/70 px-3 py-2">
            <span>Allow natural gas systems</span>
            <input
              className="h-4 w-4 accent-emerald-700"
              type="checkbox"
              checked={state.spec.allow_gas}
              onChange={(e) => updateSpec("allow_gas", e.target.checked)}
            />
          </label>
        </div>
      </fieldset>

      <fieldset className="section-card">
        <div className="section-heading">
          <span className="section-badge">3</span>
          <div>
            <legend className="text-sm font-semibold text-stone-800">Lot / site</legend>
            <p className="text-xs text-stone-500">Required — used to check placement and solar exposure.</p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <Field label="Lot width (E–W, m)" required>
            <input
              type="number"
              className="input"
              placeholder="e.g. 20"
              value={state.site.lot_width_m}
              onChange={(e) => updateSite("lot_width_m", Number(e.target.value))}
            />
          </Field>
          <Field label="Lot depth (N–S, m)" required>
            <input
              type="number"
              className="input"
              placeholder="e.g. 30"
              value={state.site.lot_depth_m}
              onChange={(e) => updateSite("lot_depth_m", Number(e.target.value))}
            />
          </Field>
          <Field label="Street-facing side" required>
            <select
              className="input"
              value={state.site.street_side}
              onChange={(e) => updateSite("street_side", e.target.value as SiteSpecInput["street_side"])}
            >
              <option value="N">North</option>
              <option value="S">South</option>
              <option value="E">East</option>
              <option value="W">West</option>
            </select>
          </Field>
          <Field
            label="Setbacks front / side / rear (m)"
            required
            hint="Minimum required clearance from lot lines."
            className="col-span-2"
          >
            <div className="grid grid-cols-3 gap-2">
              <input
                type="number"
                className="input"
                placeholder="Front"
                value={state.site.front_setback_m}
                onChange={(e) => updateSite("front_setback_m", Number(e.target.value))}
              />
              <input
                type="number"
                className="input"
                placeholder="Side"
                value={state.site.side_setback_m}
                onChange={(e) => updateSite("side_setback_m", Number(e.target.value))}
              />
              <input
                type="number"
                className="input"
                placeholder="Rear"
                value={state.site.rear_setback_m}
                onChange={(e) => updateSite("rear_setback_m", Number(e.target.value))}
              />
            </div>
          </Field>
        </div>
      </fieldset>

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-xl bg-emerald-700 px-4 py-3 text-sm font-semibold text-white shadow-xl shadow-emerald-900/15 transition hover:-translate-y-0.5 hover:bg-emerald-800 disabled:translate-y-0 disabled:opacity-50"
      >
        {submitting ? "Evaluating..." : "Evaluate project"}
      </button>
    </form>
  );
}

function Field({
  label,
  children,
  required,
  optional,
  hint,
  className,
}: {
  label: string;
  children: React.ReactNode;
  required?: boolean;
  optional?: boolean;
  hint?: string;
  className?: string;
}) {
  return (
    <label className={`block text-xs ${className ?? ""}`}>
      <span className="mb-1.5 flex items-center gap-1.5 font-medium text-stone-500">
        {label}
        {required && (
          <span className="text-[10px] font-semibold text-emerald-600" title="Required" aria-label="required">
            *
          </span>
        )}
        {optional && (
          <span className="rounded-full bg-stone-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-stone-400">
            Optional
          </span>
        )}
      </span>
      {children}
      {hint && <span className="mt-1 block text-[10px] leading-4 text-stone-400">{hint}</span>}
    </label>
  );
}

function stripUndefined<T extends object>(obj: T): Partial<T> {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null)) as Partial<T>;
}
