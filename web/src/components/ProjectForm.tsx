"use client";

import { useEffect, useState } from "react";
import {
  fetchArchetypes,
  fetchCatalog,
  fetchLocations,
  runParseSpec,
  ArchetypeInfo,
  FieldError,
  OptimizationWeights,
  ProjectSpecInput,
  SiteSpecInput,
} from "@/lib/api";
import LocationInfoPanel from "@/components/LocationInfoPanel";
import LotPicker from "@/components/LotPicker";
import WizardChrome, {
  Field,
  FieldErrorContext,
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

export type FormState = {
  spec: ProjectSpecInput;
  site: SiteSpecInput;
  weights: OptimizationWeights;
  // Brief-level hard constraint checked against catalog designs only; the
  // engine has no bedroom model for custom geometry.
  minBedrooms: number;
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
    location: "Pickering (Dunbarton)",
    num_units: 1,
    has_ac: true,
    allow_gas: true,
    excluded_mechanical_ids: [],
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
  minBedrooms: 0,
};

const STEPS: WizardStep[] = [
  { label: "Brief", caption: "Project inputs" },
  { label: "Site", caption: "Planning context" },
  { label: "Design", caption: "Catalog selection" },
  { label: "Systems", caption: "Performance setup" },
  { label: "Priorities", caption: "Review + rank" },
];

// The step each API field is entered on, so an error can send the user back to it.
export const PROJECT_FIELD_STEP: Record<string, number> = {
  location: 0, typology: 0, storeys: 0, floor_area_m2: 0,
  lot_width_m: 1, lot_depth_m: 1, street_side: 1, front_setback_m: 1,
  side_setback_m: 1, rear_setback_m: 1, latitude: 1, longitude: 1,
  orientation: 2, footprint_length_m: 2, footprint_width_m: 2,
  target_label: 3, budget_per_unit: 3, window_to_wall_ratio: 3,
  solar_option_id: 3, mechanical_option_id: 3,
};

export default function ProjectForm({
  onSubmit,
  submitting,
  initialSite,
  error,
}: {
  onSubmit: (state: FormState) => void;
  submitting: boolean;
  // An evaluation error; one naming a field sends the user back to it.
  error?: FieldError | null;
  // A lot chosen on the zoning map; the form opens on its Site step.
  initialSite?: Partial<SiteSpecInput> | null;
}) {
  const [state, setState] = useState<FormState>(() =>
    initialSite ? { ...DEFAULT_STATE, site: { ...DEFAULT_STATE.site, ...initialSite } } : DEFAULT_STATE,
  );
  const u = useUnits();
  const [step, setStep] = useState(initialSite ? 1 : 0);
  const [locations, setLocations] = useState<string[]>([]);
  const [solarOptions, setSolarOptions] = useState<
    { id: string; name: string }[]
  >([]);
  const [mechanicalOptions, setMechanicalOptions] = useState<
    { id: string; name: string; type: string }[]
  >([]);
  const [archetypes, setArchetypes] = useState<ArchetypeInfo[]>([]);
  const [selectedDesign, setSelectedDesign] = useState("");
  const [showAiAssist, setShowAiAssist] = useState(false);
  const [freeform, setFreeform] = useState("");
  const [parsing, setParsing] = useState(false);
  const [assumptions, setAssumptions] = useState<string[]>([]);
  const [parseError, setParseError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<FieldError | null>(null);

  // A new error that names one of this form's fields sends the user to its step.
  const [seenError, setSeenError] = useState(error);
  if (error !== seenError) {
    setSeenError(error);
    const target = error?.field ? PROJECT_FIELD_STEP[error.field] : undefined;
    setFieldError(target === undefined ? null : error!);
    if (target !== undefined) setStep(target);
  }
  // Editing the field the error named clears it.
  const touch = (key: string) =>
    setFieldError((current) => (current?.field === key ? null : current));

  useEffect(() => {
    fetchLocations()
      .then(setLocations)
      .catch(() => setLocations([]));
    fetchCatalog()
      .then((catalog) => {
        setSolarOptions(catalog.solar);
        setMechanicalOptions(catalog.mechanical);
      })
      .catch(() => setSolarOptions([]));
    fetchArchetypes()
      .then(setArchetypes)
      .catch(() => setArchetypes([]));
  }, []);

  const updateSpec = <K extends keyof ProjectSpecInput>(
    key: K,
    value: ProjectSpecInput[K],
  ) => {
    touch(key);
    setState((current) => ({
      ...current,
      spec: { ...current.spec, [key]: value },
    }));
  };
  const updateSite = <K extends keyof SiteSpecInput>(
    key: K,
    value: SiteSpecInput[K],
  ) => {
    touch(key);
    setState((current) => ({
      ...current,
      site: { ...current.site, [key]: value },
    }));
  };
  const updateWeight = (key: keyof OptimizationWeights, value: number) =>
    setState((current) => ({
      ...current,
      weights: { ...current.weights, [key]: value },
    }));

  const meetsBedrooms = (design: ArchetypeInfo) =>
    design.bedrooms >= state.minBedrooms;

  function setMinBedrooms(value: number) {
    setState((current) => ({ ...current, minBedrooms: value }));
    const design = archetypes.find((candidate) => candidate.id === selectedDesign);
    if (design && design.bedrooms < value) setSelectedDesign("");
  }

  function toggleExcludedSystem(id: string, excluded: boolean) {
    setState((current) => {
      const ids = new Set(current.spec.excluded_mechanical_ids);
      if (excluded) ids.add(id);
      else ids.delete(id);
      return {
        ...current,
        spec: {
          ...current.spec,
          excluded_mechanical_ids: [...ids],
          mechanical_option_id:
            excluded && current.spec.mechanical_option_id === id
              ? null
              : current.spec.mechanical_option_id,
        },
      };
    });
  }

  const usableSystems = mechanicalOptions.filter(
    (option) =>
      (state.spec.allow_gas || option.type !== "gas") &&
      !state.spec.excluded_mechanical_ids.includes(option.id),
  );

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
        minBedrooms: current.minBedrooms,
      }));
      setAssumptions(parsed.assumptions ?? []);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "Parsing failed");
    } finally {
      setParsing(false);
    }
  }

  // Why the current step can't continue yet, or null when it can.
  const blocker =
    step === 0
      ? !state.spec.location
        ? "Choose a location to continue."
        : !(state.spec.storeys > 0)
          ? "Enter at least 1 storey to continue."
          : !(state.spec.floor_area_m2 > 0)
            ? "Enter a floor area to continue."
            : null
      : step === 1
        ? !(state.site.lot_width_m > 0)
          ? "Enter the lot width to continue."
          : !(state.site.lot_depth_m > 0)
            ? "Enter the lot depth to continue."
            : null
        : step === 3
          ? !(state.spec.budget_per_unit > 0)
            ? "Enter a budget per unit to continue."
            : mechanicalOptions.length > 0 && usableSystems.length === 0
              ? "Allow at least one mechanical system to continue."
              : null
          : null;

  return (
    <FieldErrorContext.Provider value={fieldError}>
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (step === STEPS.length - 1 && !submitting) onSubmit(state);
      }}
    >
      <WizardChrome
        steps={STEPS}
        currentStep={step}
        eyebrow="Path A · Individual unit"
        title={STEPS[step].label}
        facts={[
          {
            label: "Place",
            value: (state.spec.location ?? "Choose a location").replace(
              " (Dunbarton)",
              "",
            ),
          },
          {
            label: "Home",
            value:
              u.area(state.spec.floor_area_m2) +
              " · " +
              state.spec.storeys +
              " storeys",
          },
          {
            label: "Budget",
            value: "$" + state.spec.budget_per_unit.toLocaleString(),
          },
          {
            label: "Target",
            value:
              state.spec.target_label === "nzr"
                ? "Net Zero Ready"
                : state.spec.target_label === "passive_house"
                  ? "Passive House"
                  : "Code minimum",
          },
        ]}
        guidance={
          step === 0
            ? "Start with the space you need. You can explore different designs without losing the rest of your brief."
            : step === 1
              ? state.site.latitude != null && state.site.longitude != null
                ? "The lot's size, street side and setbacks come from the parcel and by-law you chose. Any you change below are your own."
                : "Find your lot to fill its size, street side and setbacks from the City's data, or enter them yourself."
              : step === 2
                ? selectedDesign
                  ? "This design has updated your area, storeys and footprint. Check the live brief before continuing."
                  : "A custom brief keeps your current geometry. A catalog design can give you an alternative starting point."
                : step === 3
                  ? state.spec.mechanical_option_id
                    ? "You have fixed the mechanical strategy. The engine will compare configurations using this system."
                    : "Leaving the mechanical strategy open lets the engine compare available systems against your target and budget."
                  : "Higher weights give an objective more influence. The engine normalizes your priorities before ranking feasible options."
        }
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
        onNext={() =>
          setStep((current) => Math.min(STEPS.length - 1, current + 1))
        }
        nextDisabled={blocker !== null}
        nextHint={blocker}
        nextLabel={step === STEPS.length - 2 ? "Set priorities" : "Continue"}
        isLastStep={step === STEPS.length - 1}
        submitting={submitting}
        submitLabel="Evaluate individual unit"
      >
        {step === 0 && (
          <div className="space-y-5">
            <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-lime-50/80 p-4">
              <button
                type="button"
                onClick={() => setShowAiAssist((value) => !value)}
                className="flex w-full items-center justify-between text-left"
              >
                <span>
                  <span className="text-xs font-semibold text-emerald-900">
                    ✨ AI-assisted brief
                  </span>
                  <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-[13px] font-semibold uppercase tracking-wide text-emerald-700">
                    Optional
                  </span>
                </span>
                <span className="text-[13px] font-semibold text-emerald-700">
                  {showAiAssist ? "Hide" : "Describe project"}
                </span>
              </button>
              {showAiAssist && (
                <div className="mt-3">
                  <textarea
                    className="input min-h-24 resize-none"
                    rows={3}
                    placeholder="3-bed home on a 50×120 ft lot in Toronto, budget 450k, net-zero ready…"
                    value={freeform}
                    onChange={(event) => setFreeform(event.target.value)}
                  />
                  <button
                    type="button"
                    onClick={handleParse}
                    disabled={parsing || !freeform.trim()}
                    className="mt-3 rounded-lg bg-stone-950 px-4 py-2 text-xs font-semibold text-white transition hover:bg-stone-800 disabled:opacity-40"
                  >
                    {parsing ? "Parsing…" : "Fill brief with AI"}
                  </button>
                  {parseError && (
                    <p className="mt-2 text-xs text-red-600">{parseError}</p>
                  )}
                  {assumptions.length > 0 && (
                    <ul className="mt-3 list-disc rounded-lg bg-white/80 py-2 pl-6 pr-3 text-xs text-emerald-900">
                      {assumptions.map((assumption, index) => (
                        <li key={index}>{assumption}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Location" name="location" tip="Sets the climate zone and snow and rain loads from the Ontario Building Code's climate table for this place.">
                <select
                  className="input"
                  value={state.spec.location ?? ""}
                  onChange={(event) =>
                    updateSpec("location", event.target.value)
                  }
                >
                  {locations.map((location) => (
                    <option key={location} value={location}>
                      {location}
                    </option>
                  ))}
                  {!locations.includes(state.spec.location ?? "") && (
                    <option value={state.spec.location ?? ""}>
                      {state.spec.location}
                    </option>
                  )}
                </select>
              </Field>
              <Field label="Typology" name="typology" tip="The kind of building. It decides which catalogue designs are compared.">
                <select
                  className="input"
                  value={state.spec.typology}
                  onChange={(event) =>
                    updateSpec("typology", event.target.value)
                  }
                >
                  <option value="single_family">Single family</option>
                  <option value="townhouse">Townhouse</option>
                  <option value="murb">MURB</option>
                </select>
              </Field>
              <Field label="Storeys" name="storeys" tip="Floors above grade, 1 to 12. The floor area is split across them to size the footprint.">
                <input
                  type="number"
                  className="input"
                  min={1}
                  value={state.spec.storeys}
                  onChange={(event) =>
                    updateSpec("storeys", Number(event.target.value))
                  }
                />
              </Field>
              <Field label={`Floor area (${u.areaUnit})`} name="floor_area_m2" tip="Total heated floor area across all storeys, not the footprint.">
                <input
                  type="number"
                  className="input"
                  min={1}
                  value={u.areaInput(state.spec.floor_area_m2)}
                  onChange={(event) =>
                    updateSpec(
                      "floor_area_m2",
                      u.areaFromInput(Number(event.target.value)),
                    )
                  }
                />
              </Field>
              <Field label="Minimum bedrooms" tip="Designs with fewer bedrooms than this are left out.">
                <select
                  className="input"
                  value={state.minBedrooms}
                  onChange={(event) =>
                    setMinBedrooms(Number(event.target.value))
                  }
                >
                  <option value={0}>No minimum</option>
                  {[1, 2, 3].map((count) => (
                    <option key={count} value={count}>
                      {count}+
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-5">
            <LotPicker
              initialSite={initialSite}
              lotWidth={state.site.lot_width_m}
              lotDepth={state.site.lot_depth_m}
              onLotResize={(width, depth) =>
                setState((current) => ({
                  ...current,
                  site: { ...current.site, lot_width_m: width, lot_depth_m: depth },
                }))
              }
              onLot={(lot) =>
                setState((current) => ({
                  ...current,
                  site: { ...current.site, ...lot },
                }))
              }
            />
            <LocationInfoPanel
              location={state.spec.location}
              latitude={state.site.latitude}
              longitude={state.site.longitude}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={`Lot width (E–W, ${u.lengthUnit})`} name="lot_width_m" tip={"Lot frontage measured east to west. Filled in from the City's lot outline when you pick a lot."}>
                <input
                  type="number"
                  className="input"
                  min={u.lengthInput(5)}
                  step="any"
                  value={u.lengthInput(state.site.lot_width_m)}
                  onChange={(event) =>
                    updateSite(
                      "lot_width_m",
                      u.lengthFromInput(Number(event.target.value)),
                    )
                  }
                />
              </Field>
              <Field label={`Lot depth (N–S, ${u.lengthUnit})`} name="lot_depth_m" tip={"Lot depth measured north to south. Filled in from the City's lot outline when you pick a lot."}>
                <input
                  type="number"
                  className="input"
                  min={u.lengthInput(5)}
                  step="any"
                  value={u.lengthInput(state.site.lot_depth_m)}
                  onChange={(event) =>
                    updateSite(
                      "lot_depth_m",
                      u.lengthFromInput(Number(event.target.value)),
                    )
                  }
                />
              </Field>
            </div>
            <div>
              <p className="text-xs font-medium text-stone-600">
                Street-facing side
              </p>
              <div className="mt-2 grid grid-cols-4 gap-2">
                {(["N", "S", "E", "W"] as const).map((direction) => (
                  <button
                    key={direction}
                    type="button"
                    onClick={() => updateSite("street_side", direction)}
                    aria-pressed={state.site.street_side === direction}
                    className={`rounded-xl border py-3 text-xs font-semibold transition ${state.site.street_side === direction ? "border-emerald-500 bg-emerald-50 text-emerald-800 shadow-sm" : "border-stone-200 bg-white text-stone-600 hover:border-emerald-300"}`}
                  >
                    {direction}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              {(
                ["front_setback_m", "side_setback_m", "rear_setback_m"] as const
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
                    value={u.lengthInput(state.site[key])}
                    onChange={(event) =>
                      updateSite(
                        key,
                        u.lengthFromInput(Number(event.target.value)),
                      )
                    }
                  />
                </Field>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Latitude (optional)" name="latitude" tip="Filled in when you pick a lot. Used to look up zoning and solar exposure for the exact spot.">
                <input
                  type="number"
                  className="input"
                  step="any"
                  value={state.site.latitude ?? ""}
                  onChange={(event) =>
                    updateSite(
                      "latitude",
                      event.target.value ? Number(event.target.value) : null,
                    )
                  }
                />
              </Field>
              <Field label="Longitude (optional)" name="longitude" tip="Filled in when you pick a lot. Used to look up zoning and solar exposure for the exact spot.">
                <input
                  type="number"
                  className="input"
                  step="any"
                  value={state.site.longitude ?? ""}
                  onChange={(event) =>
                    updateSite(
                      "longitude",
                      event.target.value ? Number(event.target.value) : null,
                    )
                  }
                />
              </Field>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setSelectedDesign("")}
                aria-pressed={!selectedDesign}
                className={`rounded-2xl border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md ${!selectedDesign ? "border-emerald-400 bg-gradient-to-br from-emerald-50 to-lime-50 shadow-sm" : "border-stone-200 bg-white"}`}
              >
                <p className="text-sm font-semibold text-stone-900">
                  Custom brief
                </p>
                <p className="mt-1 text-[13px] leading-4 text-stone-500">
                  Keep your project inputs and shape the form manually.
                </p>
                {state.minBedrooms > 0 && (
                  <p className="mt-2 text-[13px] font-semibold text-amber-700">
                    Bedrooms not verified
                  </p>
                )}
              </button>
              {archetypes.map((design) => (
                <button
                  type="button"
                  key={design.id}
                  onClick={() => applyDesign(design.id)}
                  disabled={!meetsBedrooms(design)}
                  aria-pressed={selectedDesign === design.id}
                  className={`rounded-2xl border p-4 text-left transition enabled:hover:-translate-y-0.5 enabled:hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 ${selectedDesign === design.id ? "border-emerald-400 bg-gradient-to-br from-emerald-50 to-lime-50 shadow-sm" : "border-stone-200 bg-white"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-semibold text-stone-900">
                      {design.name}
                    </p>
                    {selectedDesign === design.id && (
                      <span className="text-xs text-emerald-700">Selected</span>
                    )}
                  </div>
                  <p className="mt-1 text-[13px] leading-4 text-stone-500">
                    {u.area(design.floor_area_m2)} · {design.storeys} storey
                    {design.storeys === 1 ? "" : "s"} · {design.bedrooms}{" "}
                    bedroom{design.bedrooms === 1 ? "" : "s"}
                    {design.units_per_building > 1 ? " minimum per home" : ""}
                  </p>
                  {state.minBedrooms > 0 && (
                    <p
                      className={`mt-2 text-[13px] font-semibold ${meetsBedrooms(design) ? "text-emerald-700" : "text-stone-500"}`}
                    >
                      {meetsBedrooms(design)
                        ? `Meets ${state.minBedrooms}+ bedrooms`
                        : `Fewer than ${state.minBedrooms} bedrooms`}
                    </p>
                  )}
                  <div className="mt-4 h-1 rounded-full bg-gradient-to-r from-emerald-500 to-lime-400 opacity-70" />
                </button>
              ))}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Orientation" name="orientation" tip="The direction the main side, with most of the windows, faces. It changes solar gain and heating need.">
                <select
                  className="input"
                  value={state.spec.orientation}
                  onChange={(event) =>
                    updateSpec(
                      "orientation",
                      event.target.value as ProjectSpecInput["orientation"],
                    )
                  }
                >
                  <option value="N">North</option>
                  <option value="S">South</option>
                  <option value="E">East</option>
                  <option value="W">West</option>
                </select>
              </Field>
              <Field
                label={`Footprint length × width (${u.lengthUnit})`}
                name={["footprint_length_m", "footprint_width_m"]}
                tip="Outside length and width of the ground floor. Leave blank and EnerZen uses the floor area divided by storeys."
              >
                <div className="flex gap-2">
                  <input
                    type="number"
                    className="input"
                    step="any"
                    value={
                      state.spec.footprint_length_m == null
                        ? ""
                        : u.lengthInput(state.spec.footprint_length_m)
                    }
                    onChange={(event) =>
                      updateSpec(
                        "footprint_length_m",
                        u.lengthFromInput(Number(event.target.value)),
                      )
                    }
                  />
                  <input
                    type="number"
                    className="input"
                    step="any"
                    value={
                      state.spec.footprint_width_m == null
                        ? ""
                        : u.lengthInput(state.spec.footprint_width_m)
                    }
                    onChange={(event) =>
                      updateSpec(
                        "footprint_width_m",
                        u.lengthFromInput(Number(event.target.value)),
                      )
                    }
                  />
                </div>
              </Field>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Energy target" name="target_label" tip="The performance level every design must reach. Higher targets need better envelopes and cost more.">
                <select
                  className="input"
                  value={state.spec.target_label}
                  onChange={(event) =>
                    updateSpec("target_label", event.target.value)
                  }
                >
                  <option value="code">Code minimum</option>
                  <option value="nzr">Net Zero Ready</option>
                  <option value="passive_house">Passive House</option>
                </select>
              </Field>
              <Field label="Budget per unit (CAD)" name="budget_per_unit" tip="Most you would spend on construction for one home, Class D. Designs that cost more are rejected.">
                <input
                  type="number"
                  className="input"
                  min={1}
                  value={state.spec.budget_per_unit}
                  onChange={(event) =>
                    updateSpec("budget_per_unit", Number(event.target.value))
                  }
                />
              </Field>
              <Field label="Window-to-wall ratio" name="window_to_wall_ratio" tip="Share of the outside wall that is window, from 0 to 1. 0.2 means 20%. More glass adds daylight and solar gain but loses more heat.">
                <input
                  type="number"
                  className="input"
                  step={0.05}
                  min={0}
                  max={1}
                  value={state.spec.window_to_wall_ratio}
                  onChange={(event) =>
                    updateSpec(
                      "window_to_wall_ratio",
                      Number(event.target.value),
                    )
                  }
                />
              </Field>
              <Field label="Solar option" name="solar_option_id" tip="Rooftop solar panels to offset the home's electricity use.">
                <select
                  className="input"
                  value={state.spec.solar_option_id}
                  onChange={(event) =>
                    updateSpec("solar_option_id", event.target.value)
                  }
                >
                  {solarOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Mechanical strategy" name="mechanical_option_id" tip="Heating, cooling and ventilation equipment. It drives energy use and operating cost.">
                <select
                  className="input"
                  value={state.spec.mechanical_option_id ?? ""}
                  onChange={(event) =>
                    updateSpec(
                      "mechanical_option_id",
                      event.target.value || null,
                    )
                  }
                >
                  <option value="">Optimize across catalog</option>
                  {usableSystems.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Toggle
                label="Include air conditioning"
                checked={state.spec.has_ac}
                onChange={(value) => updateSpec("has_ac", value)}
              />
              <Toggle
                label="Allow natural gas systems"
                checked={state.spec.allow_gas}
                onChange={(value) => updateSpec("allow_gas", value)}
              />
            </div>
            {mechanicalOptions.length > 0 && (
              <fieldset className="rounded-xl border border-stone-200 bg-white px-4 py-3">
                <legend className="px-1 text-xs font-medium text-stone-500">
                  Exclude mechanical systems
                </legend>
                <p className="text-[13px] leading-4 text-stone-400">
                  Excluded systems are never considered, whatever their score.
                </p>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {mechanicalOptions.map((option) => {
                    const gasBlocked = !state.spec.allow_gas && option.type === "gas";
                    return (
                      <label
                        key={option.id}
                        className={`flex items-center gap-2 text-xs ${gasBlocked ? "text-stone-300" : "text-stone-600"}`}
                      >
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-emerald-700"
                          disabled={gasBlocked}
                          checked={
                            gasBlocked ||
                            state.spec.excluded_mechanical_ids.includes(option.id)
                          }
                          onChange={(event) =>
                            toggleExcludedSystem(option.id, event.target.checked)
                          }
                        />
                        <span>{option.name}</span>
                      </label>
                    );
                  })}
                </div>
                {usableSystems.length === 0 && (
                  <p className="mt-2 text-xs text-red-600">
                    Every mechanical system is excluded. Allow at least one to
                    continue.
                  </p>
                )}
              </fieldset>
            )}
          </div>
        )}

        {step === 4 && (
          <div className="space-y-5">
            <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-lime-50 p-5">
              <p className="eyebrow">Ready for evaluation</p>
              <h3 className="mt-2 text-xl font-semibold tracking-tight text-stone-950">
                A brief the engine can explain.
              </h3>
              <p className="mt-2 text-sm leading-6 text-stone-600">
                EnerZen will test feasible configurations, apply the performance
                gate, rank the trade-offs, and return the recommended unit.
              </p>
            </div>
            <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
              <p className="text-xs font-semibold text-stone-800">
                Decision priorities
              </p>
              <p className="mt-1 text-[13px] leading-4 text-stone-400">
                Adjust the trade-offs used to rank configurations that pass the
                performance gate.
              </p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                {(
                  [
                    ["cost", "Capital cost"],
                    ["energy", "Operating energy"],
                    ["speed", "Construction speed"],
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
                      onChange={(event) =>
                        updateWeight(key, Number(event.target.value))
                      }
                    />
                  </label>
                ))}
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Summary
                label="Project"
                value={`${state.spec.typology.replace("_", " ")} · ${u.area(state.spec.floor_area_m2)}`}
              />
              <Summary
                label="Site"
                value={`${u.dims(state.site.lot_width_m, state.site.lot_depth_m)} · ${(state.spec.location ?? "").replace(/ \(.*\)$/, "")}`}
              />
              <Summary
                label="Target"
                value={
                  state.spec.target_label === "nzr"
                    ? "Net Zero Ready"
                    : state.spec.target_label === "passive_house"
                      ? "Passive House"
                      : "Code minimum"
                }
              />
              <Summary
                label="Priorities"
                value={`${state.weights.cost}% cost · ${state.weights.energy}% energy`}
              />
            </div>
            <div className="rounded-xl border border-stone-200 bg-stone-50/70 px-4 py-3 text-xs leading-5 text-stone-500">
              The engine will return ranked options and a site-fit view. Nothing
              is submitted until you press Evaluate individual unit.
            </div>
          </div>
        )}
      </WizardChrome>
    </form>
    </FieldErrorContext.Provider>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-3 rounded-xl border border-stone-200 bg-stone-50/70 px-4 py-3 text-xs text-stone-600">
      <span>{label}</span>
      <input
        className="h-4 w-4 accent-emerald-700"
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
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

function stripUndefined<T extends object>(object: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(object).filter(
      ([, value]) => value !== undefined && value !== null,
    ),
  ) as Partial<T>;
}
