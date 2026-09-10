import type { ConfigResult } from "@/lib/api";
import { fmtEui, fmtCarbon, fmtCad } from "@/lib/units";
import InfoTooltip from "@/components/InfoTooltip";

function Metric({
  label,
  value,
  tip,
  tone = "default",
}: {
  label: string;
  value: string;
  tip?: string;
  tone?: "default" | "accent";
}) {
  const isAccent = tone === "accent";

  return (
    <div className={isAccent ? "rounded-xl border border-emerald-300 bg-emerald-50 p-4 shadow-sm" : "tile"}>
      <div
        className={
          isAccent
            ? "flex items-center gap-1.5 text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-emerald-700"
            : "flex items-center gap-1.5 tile-label"
        }
      >
        {label}
        {tip && <InfoTooltip text={tip} />}
      </div>
      <div
        className={
          isAccent
            ? "mt-1.5 break-words text-lg font-semibold leading-tight tracking-tight text-emerald-950 sm:text-xl"
            : "tile-value"
        }
      >
        {value}
      </div>
    </div>
  );
}

export default function ResultsPanel({ results }: { results: ConfigResult[] }) {
  const top = results[0];
  const carbonPercent = Math.min(100, Math.max(0, 100 - top.embodied_carbon_kg_co2e_m2 / 5));
  const euiPercent = Math.min(100, Math.max(0, 100 - top.eui_kwh_m2_yr));

  return (
    <div className="space-y-4">
      <div className="panel overflow-hidden">
        <div className="grid gap-0 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="p-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">
                Recommended assembly
              </span>
              <span className="rounded-full bg-stone-100 px-3 py-1 text-xs font-semibold text-stone-600">
                {top.net_zero ? "Net zero" : "Low energy"}
              </span>
            </div>
            <h3 className="mt-4 text-3xl font-semibold tracking-tight text-stone-950">
              {top.wall_id} wall with {top.roof_id} roof
            </h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-stone-500">
              Optimized against cost, embodied carbon, operating energy, lifecycle performance, and NZR probability.
            </p>

            <div className="mt-5 grid grid-cols-2 gap-3">
              <Metric
                label="Construction cost"
                value={fmtCad(top.construction_cost)}
                tip="Total estimated cost to build this configuration: materials, labour, connections, finishes, mechanical, fit-out, and contingency. This is what drives your budget decision."
                tone="accent"
              />
              <Metric
                label="Build schedule"
                value={`${top.construction_weeks.toFixed(1)} wk`}
                tip="Weeks from factory fabrication through site installation to envelope close. Shorter means faster time-to-occupancy, but doesn't include interior fit-out or inspections."
              />
              <Metric
                label="EUI"
                value={fmtEui(top.eui_kwh_m2_yr)}
                tip="Energy Use Intensity — total site energy this building consumes per m² per year, across heating, cooling, hot water, and appliances. Lower means a more efficient building and a smaller utility bill."
              />
              <Metric
                label="NZR probability"
                value={`${(top.nzr_probability * 100).toFixed(0)}%`}
                tip="How often this envelope still meets the Net Zero Ready threshold when weather, airtightness, and occupant behaviour vary. Higher means the performance is robust, not just a lucky calculation."
              />
            </div>
          </div>

          <div className="border-t border-stone-200 bg-emerald-50/60 p-5 lg:border-l lg:border-t-0">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">Performance signal</p>
            <div className="mt-5 space-y-5">
              <Signal
                label="EUI efficiency"
                value={fmtEui(top.eui_kwh_m2_yr)}
                percent={euiPercent}
                tip="How this configuration's energy intensity compares on a 0-100 scale — further right means less energy consumed per m² each year."
              />
              <Signal
                label="Embodied carbon"
                value={fmtCarbon(top.embodied_carbon_kg_co2e_m2)}
                percent={carbonPercent}
                tip="Carbon emitted manufacturing the materials in this assembly — further right means fewer emissions baked into construction, before the building even operates."
              />
              <Signal
                label="NZR confidence"
                value={`${(top.nzr_probability * 100).toFixed(0)}%`}
                percent={top.nzr_probability * 100}
                tip="Same probability as above, shown as a bar so you can compare it at a glance against the other two signals."
              />
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric
          label="Embodied carbon"
          value={fmtCarbon(top.embodied_carbon_kg_co2e_m2)}
          tip="Carbon footprint of the materials themselves (cradle-to-gate), independent of how the building is operated."
        />
        <Metric
          label="Avg. monthly utility"
          value={`$${top.avg_monthly_utility.toFixed(0)}`}
          tip="Estimated average monthly electricity + gas bill, based on typical Ontario seasonal usage profiles and current regional rates."
        />
        <Metric
          label="30-yr lifecycle cost"
          value={fmtCad(top.lifecycle_cost_30yr)}
          tip="Construction cost plus 30 years of discounted energy costs. The most complete number for comparing configurations — a cheaper building to build isn't always cheaper to own."
        />
        <Metric
          label="EnerGuide score"
          value={top.energuide_score.toFixed(0)}
          tip="A 0-100 approximation of energy performance (100 = best) derived from EUI. Directional only — not an official EnerGuide rating."
        />
      </div>

      <div className="panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
          <h3 className="text-sm font-semibold text-stone-900">Top configuration options</h3>
          <span className="text-xs font-medium text-stone-400">{Math.min(results.length, 20)} shown</span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-stone-50 text-stone-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Wall</th>
                <th className="px-4 py-3 font-semibold">Roof</th>
                <th className="px-4 py-3 font-semibold">
                  <span className="flex items-center gap-1.5">
                    Cost
                    <InfoTooltip text="Total construction cost for this configuration." />
                  </span>
                </th>
                <th className="px-4 py-3 font-semibold">
                  <span className="flex items-center gap-1.5">
                    Weeks
                    <InfoTooltip text="Fabrication + installation time to envelope close." />
                  </span>
                </th>
                <th className="px-4 py-3 font-semibold">
                  <span className="flex items-center gap-1.5">
                    EUI
                    <InfoTooltip text="Energy Use Intensity, kWh per m² per year. Lower is better." />
                  </span>
                </th>
                <th className="px-4 py-3 font-semibold">
                  <span className="flex items-center gap-1.5">
                    Carbon
                    <InfoTooltip text="Embodied carbon of the materials, kgCO2e per m². Lower is better." />
                  </span>
                </th>
                <th className="px-4 py-3 font-semibold">
                  <span className="flex items-center gap-1.5">
                    30yr LCC
                    <InfoTooltip text="30-year lifecycle cost: construction plus discounted energy costs." />
                  </span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 bg-white/80">
              {results.slice(0, 20).map((r, i) => (
                <tr key={i} className={i === 0 ? "bg-emerald-50/80" : "transition hover:bg-stone-50"}>
                  <td className="px-4 py-3 font-medium text-stone-900">{r.wall_id}</td>
                  <td className="px-4 py-3 text-stone-600">{r.roof_id}</td>
                  <td className="px-4 py-3 text-stone-600">{fmtCad(r.construction_cost)}</td>
                  <td className="px-4 py-3 text-stone-600">{r.construction_weeks.toFixed(1)}</td>
                  <td className="px-4 py-3 text-stone-600">{r.eui_kwh_m2_yr.toFixed(0)}</td>
                  <td className="px-4 py-3 text-stone-600">{r.embodied_carbon_kg_co2e_m2.toFixed(0)}</td>
                  <td className="px-4 py-3 text-stone-600">{fmtCad(r.lifecycle_cost_30yr)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Signal({
  label,
  value,
  percent,
  tip,
}: {
  label: string;
  value: string;
  percent: number;
  tip?: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between gap-4 text-xs">
        <span className="flex items-center gap-1.5 font-medium text-emerald-800">
          {label}
          {tip && <InfoTooltip text={tip} />}
        </span>
        <span className="font-semibold text-stone-950">{value}</span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-emerald-100">
        <div className="h-2 rounded-full bg-emerald-600" style={{ width: `${Math.round(percent)}%` }} />
      </div>
    </div>
  );
}
