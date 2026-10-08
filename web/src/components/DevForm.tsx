"use client";

import { useEffect, useState } from "react";
import {
  fetchArchetypes,
  fetchLocations,
  ArchetypeInfo,
  DevelopmentWeights,
  DevSpecInput,
} from "@/lib/api";
import LocationInfoPanel from "@/components/LocationInfoPanel";
import WizardChrome, { WizardStep } from "@/components/WizardChrome";

const DEFAULT: DevSpecInput = {
  lot_width_m: 30,
  lot_depth_m: 50,
  street_side: "N",
  front_setback_m: 6,
  side_setback_m: 1.2,
  rear_setback_m: 7.5,
  total_budget_cad: 1500000,
  location: "Pickering (Dunbarton)",
  target_label: "nzr",
  allowed_types: ["garden_suite", "three_bhk"],
  orientation: "S",
  weights: { yield: 100, cost: 0, energy: 0, carbon: 0 },
};

const STEPS: WizardStep[] = [
  { label: "Development", caption: "Project brief" },
  { label: "Planning", caption: "Land intelligence" },
  { label: "Typology", caption: "Housing mix" },
  { label: "Priorities", caption: "Performance goals" },
  { label: "Review", caption: "Generate plan" },
];

export default function DevForm({
  onSubmit,
  submitting,
  iteration,
}: {
  onSubmit: (spec: DevSpecInput) => void;
  submitting: boolean;
  iteration: number;
}) {
  const [state, setState] = useState<DevSpecInput>(DEFAULT);
  const [step, setStep] = useState(0);
  const [locations, setLocations] = useState<string[]>([]);
  const [archetypes, setArchetypes] = useState<ArchetypeInfo[]>([]);
  const [showSetbacks, setShowSetbacks] = useState(false);

  useEffect(() => {
    fetchLocations()
      .then(setLocations)
      .catch(() => setLocations([]));
    fetchArchetypes()
      .then(setArchetypes)
      .catch(() => setArchetypes([]));
  }, []);

  function set<K extends keyof DevSpecInput>(key: K, value: DevSpecInput[K]) {
    setState((s) => ({ ...s, [key]: value }));
  }

  function toggleType(id: string) {
    setState((s) => {
      const has = s.allowed_types.includes(id);
      const next = has
        ? s.allowed_types.filter((t) => t !== id)
        : [...s.allowed_types, id];
      return { ...s, allowed_types: next };
    });
  }

  function updateWeight(key: keyof DevelopmentWeights, value: number) {
    setState((s) => ({ ...s, weights: { ...s.weights, [key]: value } }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (
      step !== STEPS.length - 1 ||
      submitting ||
      iteration >= 3 ||
      state.allowed_types.length === 0
    )
      return;
    onSubmit(state);
  }

  const canContinue =
    step === 0
      ? state.lot_width_m > 0 &&
        state.lot_depth_m > 0 &&
        state.total_budget_cad > 0
      : step === 2
        ? state.allowed_types.length > 0
        : true;
  const canSubmit = state.allowed_types.length > 0 && iteration < 3;

  return (
    <form onSubmit={handleSubmit}>
      <WizardChrome
        steps={STEPS}
        currentStep={step}
        eyebrow="Path B · Community development"
        title={STEPS[step].label}
        facts={[
          { label: "Place", value: state.location.replace(" (Dunbarton)", "") },
          {
            label: "Site area",
            value: Number.isFinite(state.lot_width_m * state.lot_depth_m)
              ? (state.lot_width_m * state.lot_depth_m).toLocaleString() + " m²"
              : "Add dimensions",
          },
          {
            label: "Budget",
            value: Number.isFinite(state.total_budget_cad)
              ? "$" + (state.total_budget_cad / 1_000_000).toFixed(2) + "M"
              : "Add budget",
          },
          {
            label: "Housing",
            value: state.allowed_types.length + " types selected",
          },
        ]}
        guidance={
          step === 0
            ? "No parcel yet? Use these dimensions to explore a scenario. You can replace them when the pilot site is selected."
            : step === 1
              ? "Street access and setbacks shape the usable area. These are planning assumptions until a parcel is confirmed."
              : step === 2
                ? state.allowed_types.length > 1
                  ? "A mix of housing types lets the engine compare more combinations. The most suitable mix depends on site fit, budget and your priorities."
                  : "One housing type keeps the brief focused. Include another if you want to compare a more varied community."
                : step === 3
                  ? state.target_label === "passive_house"
                    ? "Passive House sets an ambitious performance target. Feasibility still depends on the envelope, systems and budget."
                    : state.target_label === "nzr"
                      ? "Net Zero Ready prioritizes energy performance. It does not by itself mean the community produces all the energy it uses."
                      : "Code minimum is a useful baseline. Compare a higher performance target to explore the energy and cost trade-offs."
                  : "Next, EnerZen drafts site plan scenarios for you to review. Building performance is optimized only after you approve them, then ranked by these weights."
        }
        description={
          step === 0
            ? "Start with the development brief so EnerZen understands the parcel, budget, and place."
            : step === 1
              ? "Review the planning context that will shape where buildings, access, and landscape can go."
              : step === 2
                ? "Choose the housing types EnerZen should test as a connected community, not isolated rectangles."
                : step === 3
                  ? "Set the trade-offs that guide the sustainable community recommendation."
                  : "Confirm the brief before EnerZen generates candidate mixes and a reviewable site plan."
        }
        iteration={`Review ${Math.min(iteration + 1, 3)} of 3`}
        onBack={() => setStep((current) => Math.max(0, current - 1))}
        onNext={() =>
          setStep((current) => Math.min(STEPS.length - 1, current + 1))
        }
        nextDisabled={step === STEPS.length - 1 ? !canSubmit : !canContinue}
        nextLabel={step === 3 ? "Review brief" : "Continue"}
        isLastStep={step === STEPS.length - 1}
        submitLabel="Generate site plans"
        submitting={submitting}
      >
        {step === 0 && (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Location">
                <select
                  className="input"
                  value={state.location}
                  onChange={(e) => set("location", e.target.value)}
                >
                  {locations.map((location) => (
                    <option key={location} value={location}>
                      {location}
                    </option>
                  ))}
                  {!locations.includes(state.location) && (
                    <option value={state.location}>{state.location}</option>
                  )}
                </select>
              </Field>
              <Field label="Total budget (CAD)">
                <input
                  type="number"
                  className="input"
                  min={100000}
                  step={50000}
                  value={state.total_budget_cad}
                  onChange={(e) =>
                    set("total_budget_cad", parseFloat(e.target.value))
                  }
                />
                <p className="mt-1 text-[10px] text-stone-400">
                  ${(state.total_budget_cad / 1_000_000).toFixed(2)}M planning
                  envelope
                </p>
              </Field>
            </div>
            <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 to-lime-50/60 p-4">
              <p className="text-xs font-semibold text-emerald-900">
                Parcel starting point
              </p>
              <p className="mt-1 text-xs leading-5 text-emerald-900/65">
                Dimensions, access, and a realistic budget give the site-plan
                generator the context it needs to produce a plausible community
                concept.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Lot width (E–W, m)">
                <input
                  type="number"
                  className="input"
                  min={5}
                  max={500}
                  step={0.5}
                  value={state.lot_width_m}
                  onChange={(e) =>
                    set("lot_width_m", parseFloat(e.target.value))
                  }
                />
              </Field>
              <Field label="Lot depth (N–S, m)">
                <input
                  type="number"
                  className="input"
                  min={5}
                  max={500}
                  step={0.5}
                  value={state.lot_depth_m}
                  onChange={(e) =>
                    set("lot_depth_m", parseFloat(e.target.value))
                  }
                />
              </Field>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-5">
            <LocationInfoPanel location={state.location} />
            <div>
              <p className="text-xs font-medium text-stone-600">
                Street-facing side
              </p>
              <div className="mt-2 grid grid-cols-4 gap-2">
                {(["N", "S", "E", "W"] as const).map((direction) => (
                  <button
                    key={direction}
                    type="button"
                    onClick={() => set("street_side", direction)}
                    aria-pressed={state.street_side === direction}
                    className={`rounded-xl border py-3 text-xs font-semibold transition ${state.street_side === direction ? "border-emerald-500 bg-emerald-50 text-emerald-800 shadow-sm" : "border-stone-200 bg-white text-stone-600 hover:-translate-y-0.5 hover:border-emerald-300"}`}
                  >
                    {direction}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-stone-600">
                Solar orientation
              </p>
              <div className="mt-2 grid grid-cols-4 gap-2">
                {(["N", "S", "E", "W"] as const).map((direction) => (
                  <button
                    key={direction}
                    type="button"
                    onClick={() => set("orientation", direction)}
                    aria-pressed={state.orientation === direction}
                    className={`rounded-xl border py-3 text-xs font-semibold transition ${state.orientation === direction ? "border-lime-500 bg-lime-50 text-lime-800 shadow-sm" : "border-stone-200 bg-white text-stone-600 hover:-translate-y-0.5 hover:border-lime-300"}`}
                  >
                    Face {direction}
                  </button>
                ))}
              </div>
            </div>
            <div className="rounded-2xl border border-stone-200 bg-stone-50/70 p-4">
              <button
                type="button"
                onClick={() => setShowSetbacks((value) => !value)}
                className="flex w-full items-center justify-between text-left text-xs font-semibold text-stone-700"
              >
                <span>Planning assumptions · setbacks</span>
                <span className="text-emerald-700">
                  {showSetbacks ? "Hide" : "Edit"}
                </span>
              </button>
              {showSetbacks && (
                <div className="mt-3 grid grid-cols-3 gap-2">
                  {(
                    [
                      "front_setback_m",
                      "side_setback_m",
                      "rear_setback_m",
                    ] as const
                  ).map((key) => (
                    <label
                      key={key}
                      className="text-[10px] capitalize text-stone-400"
                    >
                      {key.replace("_setback_m", "")} (m)
                      <input
                        type="number"
                        className="input mt-1"
                        min={0}
                        step={0.1}
                        value={state[key]}
                        onChange={(e) => set(key, parseFloat(e.target.value))}
                      />
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="rounded-2xl border border-stone-200 bg-stone-50/70 p-4">
              <p className="text-xs font-semibold text-stone-800">
                What should this community include?
              </p>
              <p className="mt-1 text-xs leading-5 text-stone-500">
                Select multiple types so EnerZen can test a housing mix against
                the parcel and your priorities.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {archetypes.map((archetype) => {
                const checked = state.allowed_types.includes(archetype.id);
                const description =
                  archetype.units_per_building > 1
                    ? `${archetype.units_per_building} units per building`
                    : `${archetype.floor_area_m2} m² · ${archetype.storeys} storey${archetype.storeys === 1 ? "" : "s"}`;
                return (
                  <label
                    key={archetype.id}
                    className={`group cursor-pointer rounded-2xl border p-4 transition hover:-translate-y-0.5 hover:shadow-md ${checked ? "border-emerald-400 bg-gradient-to-br from-emerald-50 to-lime-50 shadow-sm" : "border-stone-200 bg-white hover:border-emerald-200"}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p
                          className={`text-sm font-semibold ${checked ? "text-emerald-900" : "text-stone-700"}`}
                        >
                          {archetype.name}
                        </p>
                        <p className="mt-1 text-[10px] leading-4 text-stone-400">
                          {description}
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        className="mt-1 h-4 w-4 rounded accent-emerald-600"
                        checked={checked}
                        onChange={() => toggleType(archetype.id)}
                      />
                    </div>
                    <div
                      className={`mt-4 h-1 rounded-full ${checked ? "bg-gradient-to-r from-emerald-500 to-lime-400" : "bg-stone-100"}`}
                    />
                  </label>
                );
              })}
            </div>
            {state.allowed_types.length === 0 && (
              <p className="text-xs text-red-500">
                Select at least one unit type to continue.
              </p>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="space-y-5">
            <div>
              <p className="text-xs font-medium text-stone-600">
                Target performance
              </p>
              <div className="mt-2 grid grid-cols-3 gap-2">
                {[
                  { id: "code", label: "Code" },
                  { id: "nzr", label: "Net Zero Ready" },
                  { id: "passive_house", label: "Passive House" },
                ].map((target) => (
                  <button
                    key={target.id}
                    type="button"
                    onClick={() => set("target_label", target.id)}
                    aria-pressed={state.target_label === target.id}
                    className={`rounded-xl border px-2 py-3 text-[11px] font-semibold transition ${state.target_label === target.id ? "border-emerald-500 bg-emerald-50 text-emerald-800 shadow-sm" : "border-stone-200 bg-white text-stone-600 hover:border-emerald-300"}`}
                  >
                    {target.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
              <div>
                <p className="text-xs font-semibold text-stone-800">
                  Decision priorities
                </p>
                <p className="mt-1 text-[10px] leading-4 text-stone-400">
                  These weights rank feasible community scenarios. Yield, cost,
                  energy, and carbon are currently modeled.
                </p>
              </div>
              <div className="mt-4 space-y-4">
                {(
                  [
                    ["yield", "Unit yield"],
                    ["cost", "Capital cost"],
                    ["energy", "Operating energy"],
                    ["carbon", "Embodied carbon"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key} className="block text-xs">
                    <span className="mb-1 flex items-center justify-between font-medium text-stone-600">
                      <span>{label}</span>
                      <span className="font-semibold text-emerald-700">
                        {state.weights[key]}%
                      </span>
                    </span>
                    <input
                      className="w-full accent-emerald-700"
                      type="range"
                      min={0}
                      max={100}
                      step={5}
                      value={state.weights[key]}
                      onChange={(e) =>
                        updateWeight(key, Number(e.target.value))
                      }
                    />
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-5">
            <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-lime-50 p-5">
              <p className="eyebrow">Ready for the first scenario</p>
              <h3 className="mt-2 text-xl font-semibold tracking-tight text-stone-950">
                A community brief with room to reason.
              </h3>
              <p className="mt-2 text-sm leading-6 text-stone-600">
                EnerZen will use this brief to generate ranked housing mixes,
                then render the selected concept for review.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Summary
                label="Site"
                value={`${state.lot_width_m} × ${state.lot_depth_m} m · ${state.location}`}
              />
              <Summary
                label="Budget"
                value={`$${(state.total_budget_cad / 1_000_000).toFixed(2)}M`}
              />
              <Summary
                label="Housing mix"
                value={`${state.allowed_types.length} selected types`}
              />
              <Summary
                label="Performance"
                value={
                  state.target_label === "nzr"
                    ? "Net Zero Ready"
                    : state.target_label === "passive_house"
                      ? "Passive House"
                      : "Code minimum"
                }
              />
            </div>
          </div>
        )}
      </WizardChrome>
    </form>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-xs">
      <span className="mb-1.5 block font-medium text-stone-500">{label}</span>
      {children}
    </label>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-stone-200 bg-white px-4 py-3">
      <p className="tile-label">{label}</p>
      <p className="mt-1 text-sm font-semibold text-stone-900">{value}</p>
    </div>
  );
}
