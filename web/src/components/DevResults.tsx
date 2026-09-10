"use client";

import type { DevMixResult } from "@/lib/api";
import { fmtCad, fmtArea, M2 } from "@/lib/units";
import InfoTooltip from "@/components/InfoTooltip";

const ARCHETYPE_COLORS: Record<string, string> = {
  garden_suite: "bg-emerald-100 text-emerald-800",
  three_bhk:    "bg-blue-100 text-blue-800",
  murb:         "bg-pink-100 text-pink-800",
  townhouse:    "bg-amber-100 text-amber-800",
};

const ARCHETYPE_LABELS: Record<string, string> = {
  garden_suite: "Garden Suite",
  three_bhk:    "3 BHK",
  murb:         "MURB",
  townhouse:    "Townhouse",
};

// Shared column template so the header legend and every data row line up.
const METRICS_GRID = "grid grid-cols-[minmax(0,1fr)_52px_88px_84px_68px_92px] gap-3";

export default function DevResults({
  mixes,
  selectedIndex,
  onSelect,
}: {
  mixes: DevMixResult[];
  selectedIndex: number;
  onSelect: (i: number) => void;
}) {
  if (mixes.length === 0) return null;

  return (
    <div className="panel overflow-hidden">
      <div className="border-b border-stone-200 px-5 py-4">
        <p className="eyebrow">Development configurations</p>
        <h3 className="mt-1 text-xl font-semibold text-stone-950">
          {mixes.length} feasible unit mix{mixes.length > 1 ? "es" : ""} found
        </h3>
        <p className="mt-1 text-xs text-stone-500">
          Click a row to update the site plan. Ranked by total units, then energy efficiency.
        </p>
      </div>

      <div className={`${METRICS_GRID} border-b border-stone-100 bg-stone-50/60 px-5 py-2 text-[10px] font-semibold uppercase tracking-wide text-stone-400`}>
        <span />
        <span className="flex items-center justify-end gap-1 text-right">
          Units
          <InfoTooltip text="How many total dwelling units this mix places on the lot. More units generally means more revenue potential." />
        </span>
        <span className="flex items-center justify-end gap-1 text-right">
          Total cost
          <InfoTooltip text="Combined construction cost for every unit in this mix." />
        </span>
        <span className="flex items-center justify-end gap-1 text-right">
          Avg EUI
          <InfoTooltip text="Average Energy Use Intensity across the mix, kWh per m² per year. Lower is more efficient." />
        </span>
        <span className="flex items-center justify-end gap-1 text-right">
          NZR units
          <InfoTooltip text="How many of the units meet Net Zero Ready out of the total. A full ratio means the whole mix qualifies." />
        </span>
        <span className="flex items-center justify-end gap-1 text-right">
          Avg utility/mo
          <InfoTooltip text="Average estimated monthly electricity + gas bill per unit." />
        </span>
      </div>

      <div className="divide-y divide-stone-100">
        {mixes.map((mix, i) => (
          <button
            key={i}
            onClick={() => onSelect(i)}
            className={`w-full px-5 py-4 text-left transition ${
              i === selectedIndex
                ? "bg-emerald-50"
                : "bg-white hover:bg-stone-50"
            }`}
          >
            <div className={`${METRICS_GRID} items-center`}>
              <div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(mix.units).map(([id, count]) =>
                    count > 0 ? (
                      <span
                        key={id}
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                          ARCHETYPE_COLORS[id] ?? "bg-stone-100 text-stone-700"
                        }`}
                      >
                        {count}× {ARCHETYPE_LABELS[id] ?? id}
                      </span>
                    ) : null
                  )}
                </div>
                <p className="mt-1.5 text-xs text-stone-500">
                  {fmtArea(mix.total_floor_area_m2)} total built area
                </p>
              </div>

              <Metric value={String(mix.total_units)} highlight />
              <Metric value={fmtCad(mix.total_cost)} />
              <Metric value={`${mix.avg_eui_kwh_m2_yr} kWh/${M2}`} />
              <Metric
                value={`${mix.nzr_unit_count}/${mix.total_units}`}
                ok={mix.nzr_unit_count === mix.total_units}
              />
              <Metric value={fmtCad(mix.avg_monthly_utility)} />
            </div>

            {i === selectedIndex && (
              <p className="mt-2 text-[10px] font-semibold text-emerald-700">
                ✓ Showing site plan for this configuration
              </p>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

function Metric({
  value,
  highlight,
  ok,
}: {
  value: string;
  highlight?: boolean;
  ok?: boolean;
}) {
  const color =
    ok === true ? "text-emerald-700" :
    ok === false ? "text-amber-600" :
    highlight ? "text-stone-950" : "text-stone-700";

  return <p className={`text-right text-sm font-semibold ${color}`}>{value}</p>;
}
