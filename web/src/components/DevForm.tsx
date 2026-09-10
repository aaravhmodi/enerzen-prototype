"use client";

import { useEffect, useState } from "react";
import { fetchLocations, DevSpecInput } from "@/lib/api";
import LocationInfoPanel from "@/components/LocationInfoPanel";

const ARCHETYPE_OPTIONS = [
  { id: "garden_suite", label: "Garden Suite (1 BR)", desc: "46 m² · 1 storey" },
  { id: "three_bhk",   label: "3-Bedroom Unit",      desc: "163 m² · 2 storeys" },
  { id: "murb",        label: "MURB (6-storey)",      desc: "24 units per building" },
  { id: "townhouse",   label: "Townhouse (3 BR)",     desc: "150 m²/unit · attached" },
];

const DEFAULT: DevSpecInput = {
  lot_width_m: 30,
  lot_depth_m: 50,
  street_side: "N",
  front_setback_m: 6,
  side_setback_m: 1.2,
  rear_setback_m: 7.5,
  total_budget_cad: 1500000,
  location: "Toronto",
  target_label: "nzr",
  allowed_types: ["garden_suite", "three_bhk"],
  orientation: "S",
};

export default function DevForm({
  onSubmit,
  submitting,
}: {
  onSubmit: (spec: DevSpecInput) => void;
  submitting: boolean;
}) {
  const [state, setState] = useState<DevSpecInput>(DEFAULT);
  const [locations, setLocations] = useState<string[]>([]);
  const [showSetbacks, setShowSetbacks] = useState(false);

  useEffect(() => {
    fetchLocations().then(setLocations).catch(() => setLocations([]));
  }, []);

  function set<K extends keyof DevSpecInput>(key: K, value: DevSpecInput[K]) {
    setState((s) => ({ ...s, [key]: value }));
  }

  function toggleType(id: string) {
    setState((s) => {
      const has = s.allowed_types.includes(id);
      const next = has ? s.allowed_types.filter((t) => t !== id) : [...s.allowed_types, id];
      return { ...s, allowed_types: next };
    });
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (state.allowed_types.length === 0) return;
    onSubmit(state);
  }

  const canSubmit = !submitting && state.allowed_types.length > 0;

  return (
    <form onSubmit={handleSubmit} className="panel space-y-5 p-5">
      <div>
        <p className="eyebrow">Development planner</p>
        <h2 className="mt-1 text-xl font-semibold text-stone-950">Site + unit mix</h2>
      </div>

      {/* Location */}
      <div className="space-y-1">
        <label className="text-xs font-medium text-stone-600">Location</label>
        <select
          className="input"
          value={state.location}
          onChange={(e) => set("location", e.target.value)}
        >
          {locations.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
          {!locations.includes(state.location) && (
            <option value={state.location}>{state.location}</option>
          )}
        </select>
        <LocationInfoPanel location={state.location} />
      </div>

      {/* Lot dimensions */}
      <div className="space-y-1">
        <label className="text-xs font-medium text-stone-600">Lot dimensions (m)</label>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-stone-400">Width (E-W)</label>
            <input
              type="number"
              className="input"
              min={5}
              max={500}
              step={0.5}
              value={state.lot_width_m}
              onChange={(e) => set("lot_width_m", parseFloat(e.target.value))}
            />
          </div>
          <div>
            <label className="text-[10px] text-stone-400">Depth (N-S)</label>
            <input
              type="number"
              className="input"
              min={5}
              max={500}
              step={0.5}
              value={state.lot_depth_m}
              onChange={(e) => set("lot_depth_m", parseFloat(e.target.value))}
            />
          </div>
        </div>
      </div>

      {/* Street side */}
      <div className="space-y-1">
        <label className="text-xs font-medium text-stone-600">Street-facing side</label>
        <div className="grid grid-cols-4 gap-1.5">
          {(["N", "S", "E", "W"] as const).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => set("street_side", d)}
              className={`rounded-lg border py-2 text-xs font-semibold transition ${
                state.street_side === d
                  ? "border-emerald-500 bg-emerald-50 text-emerald-800"
                  : "border-stone-200 bg-white text-stone-600 hover:border-emerald-300"
              }`}
            >
              {d}
            </button>
          ))}
        </div>
      </div>

      {/* Total budget */}
      <div className="space-y-1">
        <label className="text-xs font-medium text-stone-600">Total budget (CAD)</label>
        <input
          type="number"
          className="input"
          min={100000}
          step={50000}
          value={state.total_budget_cad}
          onChange={(e) => set("total_budget_cad", parseFloat(e.target.value))}
        />
        <p className="text-[10px] text-stone-400">
          ${(state.total_budget_cad / 1_000_000).toFixed(2)}M
        </p>
      </div>

      {/* Unit types */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-stone-600">Unit types to include</label>
        <div className="space-y-1.5">
          {ARCHETYPE_OPTIONS.map((opt) => {
            const checked = state.allowed_types.includes(opt.id);
            return (
              <label
                key={opt.id}
                className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2.5 transition ${
                  checked
                    ? "border-emerald-400 bg-emerald-50"
                    : "border-stone-200 bg-white hover:border-stone-300"
                }`}
              >
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded accent-emerald-600"
                  checked={checked}
                  onChange={() => toggleType(opt.id)}
                />
                <div>
                  <p className={`text-xs font-semibold ${checked ? "text-emerald-800" : "text-stone-700"}`}>
                    {opt.label}
                  </p>
                  <p className="text-[10px] text-stone-400">{opt.desc}</p>
                </div>
              </label>
            );
          })}
        </div>
        {state.allowed_types.length === 0 && (
          <p className="text-[11px] text-red-500">Select at least one unit type.</p>
        )}
      </div>

      {/* Energy target */}
      <div className="space-y-1">
        <label className="text-xs font-medium text-stone-600">Energy target</label>
        <div className="grid grid-cols-3 gap-1.5">
          {[
            { id: "code", label: "Code" },
            { id: "nzr", label: "Net Zero Ready" },
            { id: "passive_house", label: "Passive House" },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => set("target_label", t.id)}
              className={`rounded-lg border py-2 text-[11px] font-semibold transition ${
                state.target_label === t.id
                  ? "border-emerald-500 bg-emerald-50 text-emerald-800"
                  : "border-stone-200 bg-white text-stone-600 hover:border-emerald-300"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Setbacks (collapsible) */}
      <div>
        <button
          type="button"
          onClick={() => setShowSetbacks((v) => !v)}
          className="flex items-center gap-1 text-xs font-medium text-stone-500 hover:text-stone-700"
        >
          <span>{showSetbacks ? "▾" : "▸"}</span> Setbacks
        </button>
        {showSetbacks && (
          <div className="mt-2 grid grid-cols-3 gap-2">
            {(["front_setback_m", "side_setback_m", "rear_setback_m"] as const).map((k) => (
              <div key={k}>
                <label className="text-[10px] text-stone-400 capitalize">
                  {k.replace("_setback_m", "").replace("_", " ")} (m)
                </label>
                <input
                  type="number"
                  className="input"
                  min={0}
                  step={0.1}
                  value={state[k]}
                  onChange={(e) => set(k, parseFloat(e.target.value))}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <button
        type="submit"
        disabled={!canSubmit}
        className="w-full rounded-xl bg-emerald-900 py-3 text-sm font-semibold text-white shadow-md transition hover:-translate-y-0.5 hover:bg-emerald-800 hover:shadow-lg disabled:translate-y-0 disabled:opacity-40"
      >
        {submitting ? "Optimizing…" : "Find best configurations"}
      </button>
    </form>
  );
}
