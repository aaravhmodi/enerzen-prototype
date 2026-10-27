"use client";

import { useEffect, useState } from "react";
import {
  fetchArchetypes,
  fetchCatalog,
  fetchLocations,
  placeName,
  ArchetypeInfo,
  DevelopmentWeights,
  DevSpecInput,
  FieldError,
} from "@/lib/api";
import LocationInfoPanel from "@/components/LocationInfoPanel";
import LotPicker from "@/components/LotPicker";
import WizardChrome, {
  Field,
  FieldErrorContext,
  FieldErrorText,
  WizardStep,
} from "@/components/WizardChrome";
import { useUnits } from "@/lib/units";
import InfoTooltip from "@/components/InfoTooltip";

// What each priority slider changes in the ranking.
const WEIGHT_TIPS: Record<string, string> = {
  cost: "How much lower construction cost counts when ranking options.",
  energy: "How much lower yearly energy use counts when ranking options.",
  speed: "How much faster factory and site construction counts when ranking options.",
  carbon: "How much lower embodied carbon in the materials counts when ranking options.",
  yield: "How much fitting more homes on the land counts when ranking mixes.",
};

// engine/dev_optimizer.HOUSES: the types a garden suite can sit behind.
const HOUSES = ["three_bhk", "townhouse"];

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
  weights: { yield: 25, cost: 25, energy: 25, carbon: 25 },
  min_bedrooms: 0,
  max_storeys: null,
  excluded_mechanical_ids: [],
};

const STEPS: WizardStep[] = [
  { label: "Development", caption: "Project brief" },
  { label: "Planning", caption: "Land intelligence" },
  { label: "Typology", caption: "Housing mix" },
  { label: "Priorities", caption: "Performance goals" },
  { label: "Review", caption: "Generate plan" },
];

// The step each API field is entered on, so an error can send the user back to it.
export const DEV_FIELD_STEP: Record<string, number> = {
  location: 0, total_budget_cad: 0, lot_width_m: 0, lot_depth_m: 0,
  street_side: 1, orientation: 1, front_setback_m: 1, side_setback_m: 1, rear_setback_m: 1,
  allowed_types: 2, min_bedrooms: 2, max_storeys: 2,
  target_label: 3,
};

export default function DevForm({
  onSubmit,
  submitting,
  iteration,
  error,
}: {
  onSubmit: (spec: DevSpecInput) => void;
  submitting: boolean;
  iteration: number;
  // A scenario error; one naming a field sends the user back to it.
  error?: FieldError | null;
}) {
  const u = useUnits();
  const [state, setState] = useState<DevSpecInput>(DEFAULT);
  const [step, setStep] = useState(0);
  const [locations, setLocations] = useState<string[]>([]);
  const [archetypes, setArchetypes] = useState<ArchetypeInfo[]>([]);
  const [showSetbacks, setShowSetbacks] = useState(false);
  const [mechanicalOptions, setMechanicalOptions] = useState<
    { id: string; name: string }[]
  >([]);
  const [fieldError, setFieldError] = useState<FieldError | null>(null);

  // A new error that names one of this form's fields sends the user to its step.
  const [seenError, setSeenError] = useState(error);
  if (error !== seenError) {
    setSeenError(error);
    const target = error?.field ? DEV_FIELD_STEP[error.field] : undefined;
    setFieldError(target === undefined ? null : error!);
    if (target !== undefined) setStep(target);
    if (error?.field?.endsWith("_setback_m")) setShowSetbacks(true);
  }
  // Editing the field the error named clears it.
  const touch = (key: string) =>
    setFieldError((current) => (current?.field === key ? null : current));

  useEffect(() => {
    fetchLocations()
      .then(setLocations)
      .catch(() => setLocations([]));
    fetchArchetypes()
      .then(setArchetypes)
      .catch(() => setArchetypes([]));
    fetchCatalog()
      .then((catalog) => setMechanicalOptions(catalog.mechanical))
      .catch(() => setMechanicalOptions([]));
  }, []);

  // Mirrors engine/dev_optimizer.excluded_types so the brief shows what the
  // hard constraints rule out before anything is submitted.
  function ruledOut(archetype: ArchetypeInfo): string | null {
    if (archetype.bedrooms < state.min_bedrooms)
      return `Fewer than ${state.min_bedrooms} bedrooms`;
    if (state.max_storeys !== null && archetype.storeys > state.max_storeys)
      return `Taller than ${state.max_storeys} storey${state.max_storeys === 1 ? "" : "s"}`;
    if (archetype.id === "garden_suite" && !archetypes.some((a) => HOUSES.includes(a.id)
        && state.allowed_types.includes(a.id) && ruledOut(a) === null))
      return "Needs the 3-Bedroom Unit or Townhouse: a garden suite sits behind a house";
    return null;
  }

  function toggleSystem(id: string) {
    setState((s) => ({
      ...s,
      excluded_mechanical_ids: s.excluded_mechanical_ids.includes(id)
        ? s.excluded_mechanical_ids.filter((m) => m !== id)
        : [...s.excluded_mechanical_ids, id],
    }));
  }

  const eligibleTypes = state.allowed_types.filter((id) => {
    const archetype = archetypes.find((a) => a.id === id);
    return !archetype || !ruledOut(archetype);
  });
  const systemsLeft =
    mechanicalOptions.length === 0 ||
    mechanicalOptions.some((m) => !state.excluded_mechanical_ids.includes(m.id));

  function set<K extends keyof DevSpecInput>(key: K, value: DevSpecInput[K]) {
    touch(key);
    setState((s) => ({ ...s, [key]: value }));
  }

  function toggleType(id: string) {
    touch("allowed_types");
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

  const mixBlocker =
    state.allowed_types.length === 0
      ? "Select at least one housing type to continue."
      : eligibleTypes.length === 0
        ? "Every selected type is ruled out by the bedroom or storey limits. Relax a limit or select another type."
        : !systemsLeft
          ? "Every mechanical system is excluded. Allow at least one to continue."
          : null;
  // Why the current step can't continue yet, or null when it can.
  const blocker =
    step === 0
      ? !(state.lot_width_m > 0)
        ? "Enter the lot width to continue."
        : !(state.lot_depth_m > 0)
          ? "Enter the lot depth to continue."
          : !(state.total_budget_cad > 0)
            ? "Enter a total budget to continue."
            : null
      : step === 2
        ? mixBlocker
        : step === STEPS.length - 1
          ? (mixBlocker ??
            (iteration >= 3 ? "The site plan review is limited to 3 iterations." : null))
          : null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (step !== STEPS.length - 1 || submitting || blocker) return;
    onSubmit(state);
  }

  return (
    <FieldErrorContext.Provider value={fieldError}>
    <form onSubmit={handleSubmit}>
      <WizardChrome
        steps={STEPS}
        currentStep={step}
        eyebrow="Path B · Community development"
        title={STEPS[step].label}
        facts={[
          { label: "Place", value: placeName(state.location) },
          {
            label: "Site area",
            value: Number.isFinite(state.lot_width_m * state.lot_depth_m)
              ? u.area(state.lot_width_m * state.lot_depth_m)
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
            ? "Pick a lot to fill its size, street side and setbacks from the City's data, or enter dimensions to explore a scenario."
            : step === 1
              ? state.latitude != null
                ? "Street access and setbacks shape the usable area. They come from the lot and by-law you chose; any you edit are your own."
                : "Street access and setbacks shape the usable area. These are planning assumptions until a parcel is confirmed."
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
        nextDisabled={blocker !== null}
        nextHint={blocker}
        nextLabel={step === 3 ? "Review brief" : "Continue"}
        isLastStep={step === STEPS.length - 1}
        submitLabel="Generate site plans"
        submitting={submitting}
      >
        {step === 0 && (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Location" name="location" tip="Sets the climate zone and snow and rain loads from the Ontario Building Code's climate table for this place.">
                <select
                  className="input"
                  value={state.location}
                  onChange={(e) => set("location", e.target.value)}
                >
                  {locations.map((location) => (
                    <option key={location} value={location}>
                      {placeName(location)}
                    </option>
                  ))}
                  {!locations.includes(state.location) && (
                    <option value={state.location}>{state.location}</option>
                  )}
                </select>
              </Field>
              <Field label="Total budget (CAD)" name="total_budget_cad" tip="Most you would spend on construction for every home on the lot together, Class D. Mixes above it are left out.">
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
                <p className="mt-1 text-[13px] text-stone-400">
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
            <LotPicker
              resume={state}
              lotWidth={state.lot_width_m}
              lotDepth={state.lot_depth_m}
              onLotResize={(width, depth) => setState((current) => ({ ...current, lot_width_m: width, lot_depth_m: depth }))}
              onLot={(lot) =>
                setState((current) => ({
                  ...current,
                  lot_width_m: lot.lot_width_m ?? current.lot_width_m,
                  lot_depth_m: lot.lot_depth_m ?? current.lot_depth_m,
                  street_side: lot.street_side ?? current.street_side,
                  front_setback_m: lot.front_setback_m ?? current.front_setback_m,
                  side_setback_m: lot.side_setback_m ?? current.side_setback_m,
                  rear_setback_m: lot.rear_setback_m ?? current.rear_setback_m,
                  latitude: lot.latitude,
                  longitude: lot.longitude,
                }))
              }
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={`Lot width (E–W, ${u.lengthUnit})`} name="lot_width_m" tip={"Lot frontage measured east to west. Filled in from the City's lot outline when you pick a lot."}>
                <input
                  type="number"
                  className="input"
                  min={u.lengthInput(5)}
                  max={u.lengthInput(500)}
                  step={u.lengthStep(0.5)}
                  value={u.lengthInput(state.lot_width_m)}
                  onChange={(e) =>
                    set(
                      "lot_width_m",
                      u.lengthFromInput(parseFloat(e.target.value)),
                    )
                  }
                />
              </Field>
              <Field label={`Lot depth (N–S, ${u.lengthUnit})`} name="lot_depth_m" tip={"Lot depth measured north to south. Filled in from the City's lot outline when you pick a lot."}>
                <input
                  type="number"
                  className="input"
                  min={u.lengthInput(5)}
                  max={u.lengthInput(500)}
                  step={u.lengthStep(0.5)}
                  value={u.lengthInput(state.lot_depth_m)}
                  onChange={(e) =>
                    set(
                      "lot_depth_m",
                      u.lengthFromInput(parseFloat(e.target.value)),
                    )
                  }
                />
              </Field>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-5">
            <LocationInfoPanel location={state.location} latitude={state.latitude} longitude={state.longitude} />
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
                    <Field
                      key={key}
                      name={key}
                      label={`${key.replace("_setback_m", "")} setback (${u.lengthUnit})`}
                      tip={"Distance the home must stay from the lot line on that side. Filled in from the by-law when you pick a lot; the front faces the street-facing side."}
                    >
                      <input
                        type="number"
                        className="input"
                        min={0}
                        step={u.lengthStep(0.1)}
                        value={u.lengthInput(state[key])}
                        onChange={(e) =>
                          set(key, u.lengthFromInput(parseFloat(e.target.value)))
                        }
                      />
                    </Field>
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
                const reason = ruledOut(archetype);
                const description =
                  (archetype.units_per_building > 1
                    ? `${archetype.units_per_building} units per building · ${archetype.storeys} storeys`
                    : `${u.area(archetype.floor_area_m2)} · ${archetype.storeys} storey${archetype.storeys === 1 ? "" : "s"}`) +
                  ` · ${archetype.bedrooms} bedroom${archetype.bedrooms === 1 ? "" : "s"}` +
                  (archetype.units_per_building > 1 ? " minimum" : "");
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
                        <p className="mt-1 text-[13px] leading-4 text-stone-400">
                          {description}
                        </p>
                        {checked && reason && (
                          <p className="mt-1 text-[13px] font-semibold text-amber-700">
                            Ruled out: {reason.toLowerCase()}
                          </p>
                        )}
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
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Minimum bedrooms per home" name="min_bedrooms" tip="Home types with fewer bedrooms than this are left out of the mix.">
                <select
                  className="input"
                  value={state.min_bedrooms}
                  onChange={(e) => set("min_bedrooms", Number(e.target.value))}
                >
                  <option value={0}>No minimum</option>
                  {[1, 2, 3].map((count) => (
                    <option key={count} value={count}>
                      {count}+
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Maximum storeys" name="max_storeys" tip="Home types taller than this are left out. The by-law's height limit still applies.">
                <select
                  className="input"
                  value={state.max_storeys ?? ""}
                  onChange={(e) =>
                    set("max_storeys", e.target.value ? Number(e.target.value) : null)
                  }
                >
                  <option value="">No limit</option>
                  {[1, 2, 3, 4, 5].map((count) => (
                    <option key={count} value={count}>
                      {count}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            {mechanicalOptions.length > 0 && (
              <fieldset className="rounded-2xl border border-stone-200 bg-white p-4">
                <legend className="px-1 text-xs font-medium text-stone-500">
                  Exclude mechanical systems
                </legend>
                <div className="grid gap-2 sm:grid-cols-2">
                  {mechanicalOptions.map((option) => (
                    <label key={option.id} className="flex items-center gap-2 text-xs text-stone-600">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-emerald-700"
                        checked={state.excluded_mechanical_ids.includes(option.id)}
                        onChange={() => toggleSystem(option.id)}
                      />
                      <span>{option.name}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
            {fieldError?.field === "allowed_types" && (
              <FieldErrorText error={fieldError} />
            )}
            {state.allowed_types.length === 0 ? (
              <p className="text-xs text-red-500">
                Select at least one unit type to continue.
              </p>
            ) : eligibleTypes.length === 0 ? (
              <p className="text-xs text-red-500">
                Every selected type is ruled out by the bedroom or storey
                limits. Relax a limit or select another type.
              </p>
            ) : !systemsLeft ? (
              <p className="text-xs text-red-500">
                Every mechanical system is excluded. Allow at least one to
                continue.
              </p>
            ) : null}
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
                    className={`rounded-xl border px-2 py-3 text-[13px] font-semibold transition ${state.target_label === target.id ? "border-emerald-500 bg-emerald-50 text-emerald-800 shadow-sm" : "border-stone-200 bg-white text-stone-600 hover:border-emerald-300"}`}
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
                <p className="mt-1 text-[13px] leading-4 text-stone-400">
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
                      <span className="flex items-center gap-1">
                        {label}
                        <InfoTooltip text={WEIGHT_TIPS[key]} />
                      </span>
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
                value={`${u.dims(state.lot_width_m, state.lot_depth_m)} · ${state.location.replace(/ \(.*\)$/, "")}`}
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
    </FieldErrorContext.Provider>
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
