"use client";

import type { DevMixResult } from "@/lib/api";

const ARCHETYPE_LABELS: Record<string, string> = {
  garden_suite: "Garden Suite",
  three_bhk:    "3-Bedroom Unit",
  murb:         "MURB",
  townhouse:    "Townhouse",
};

export default function MultiSitePlanView({
  svg,
  mix,
}: {
  svg: string;
  mix: DevMixResult;
}) {
  return (
    <div className="panel overflow-hidden">
      <div className="border-b border-stone-200 px-5 py-4">
        <p className="eyebrow">Development site plan</p>
        <h3 className="mt-1 text-xl font-semibold text-stone-950">
          {mix.mix_label}
        </h3>
      </div>

      <div className="grid gap-0 lg:grid-cols-[1fr_240px]">
        <div className="bg-white p-5">
          <div
            className="rounded-xl border border-stone-200 bg-stone-50 p-4 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
            dangerouslySetInnerHTML={{ __html: svg }}
          />
          <p className="mt-3 text-[10px] text-stone-400 text-center">
            Schematic placement — not to architectural scale. Setbacks shown as dashed line.
          </p>
        </div>

        <aside className="border-t border-stone-200 bg-stone-50/80 p-5 lg:border-l lg:border-t-0">
          <p className="text-xs font-semibold text-stone-500 mb-3">Unit breakdown</p>
          <dl className="space-y-2 text-xs text-stone-600">
            {Object.entries(mix.units).map(([id, count]) =>
              count > 0 ? (
                <div key={id} className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm">
                  <dt className="text-stone-400">{ARCHETYPE_LABELS[id] ?? id}</dt>
                  <dd className="mt-1 text-base font-semibold text-stone-950">{count}</dd>
                </div>
              ) : null
            )}

            <div className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm">
              <dt className="text-stone-400">Total units</dt>
              <dd className="mt-1 text-base font-semibold text-stone-950">{mix.total_units}</dd>
            </div>

            <div className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm">
              <dt className="text-stone-400">Built area</dt>
              <dd className="mt-1 text-base font-semibold text-stone-950">
                {mix.total_floor_area_m2.toLocaleString()} m²
              </dd>
            </div>

            <div className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm">
              <dt className="text-stone-400">Avg EUI</dt>
              <dd className="mt-1 text-base font-semibold text-stone-950">
                {mix.avg_eui_kwh_m2_yr} kWh/m²·yr
              </dd>
            </div>

            <div className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm">
              <dt className="text-stone-400">NZR compliant</dt>
              <dd className={`mt-1 text-base font-semibold ${
                mix.nzr_unit_count === mix.total_units ? "text-emerald-700" : "text-amber-600"
              }`}>
                {mix.nzr_unit_count}/{mix.total_units} units
              </dd>
            </div>

            <div className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm">
              <dt className="text-stone-400">Avg monthly utility</dt>
              <dd className="mt-1 text-base font-semibold text-stone-950">
                ${mix.avg_monthly_utility.toLocaleString()}/unit
              </dd>
            </div>
          </dl>
        </aside>
      </div>
    </div>
  );
}
