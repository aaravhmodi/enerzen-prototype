import type { ConfigResult } from "@/lib/api";

function Metric({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "accent" }) {
  const isAccent = tone === "accent";

  return (
    <div
      className={[
        "rounded-xl border p-4 shadow-sm",
        isAccent
          ? "border-emerald-200 bg-emerald-900 text-white shadow-emerald-900/10"
          : "border-stone-200 bg-white/90 text-stone-950",
      ].join(" ")}
    >
      <div className={isAccent ? "text-xs font-medium text-emerald-100" : "text-xs font-medium text-stone-400"}>
        {label}
      </div>
      <div className="mt-1 text-xl font-semibold tracking-tight">{value}</div>
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

            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Metric label="Construction cost" value={`$${top.construction_cost.toLocaleString()}`} tone="accent" />
              <Metric label="Build schedule" value={`${top.construction_weeks.toFixed(1)} wk`} />
              <Metric label="EUI" value={`${top.eui_kwh_m2_yr.toFixed(0)} kWh/m2/yr`} />
              <Metric label="NZR probability" value={`${(top.nzr_probability * 100).toFixed(0)}%`} />
            </div>
          </div>

          <div className="border-t border-stone-200 bg-stone-950 p-5 text-white lg:border-l lg:border-t-0">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-200">Performance signal</p>
            <div className="mt-5 space-y-5">
              <Signal label="EUI efficiency" value={`${top.eui_kwh_m2_yr.toFixed(0)} kWh/m2/yr`} percent={euiPercent} />
              <Signal
                label="Embodied carbon"
                value={`${top.embodied_carbon_kg_co2e_m2.toFixed(0)} kgCO2e/m2`}
                percent={carbonPercent}
              />
              <Signal
                label="NZR confidence"
                value={`${(top.nzr_probability * 100).toFixed(0)}%`}
                percent={top.nzr_probability * 100}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Embodied carbon" value={`${top.embodied_carbon_kg_co2e_m2.toFixed(0)} kgCO2e/m2`} />
        <Metric label="Avg. monthly utility" value={`$${top.avg_monthly_utility.toFixed(0)}`} />
        <Metric label="30-yr lifecycle cost" value={`$${top.lifecycle_cost_30yr.toLocaleString()}`} />
        <Metric label="EnerGuide score" value={top.energuide_score.toFixed(0)} />
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
                <th className="px-4 py-3 font-semibold">Cost</th>
                <th className="px-4 py-3 font-semibold">Weeks</th>
                <th className="px-4 py-3 font-semibold">EUI</th>
                <th className="px-4 py-3 font-semibold">Carbon</th>
                <th className="px-4 py-3 font-semibold">30yr LCC</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 bg-white/80">
              {results.slice(0, 20).map((r, i) => (
                <tr key={i} className={i === 0 ? "bg-emerald-50/80" : "transition hover:bg-stone-50"}>
                  <td className="px-4 py-3 font-medium text-stone-900">{r.wall_id}</td>
                  <td className="px-4 py-3 text-stone-600">{r.roof_id}</td>
                  <td className="px-4 py-3 text-stone-600">${r.construction_cost.toLocaleString()}</td>
                  <td className="px-4 py-3 text-stone-600">{r.construction_weeks.toFixed(1)}</td>
                  <td className="px-4 py-3 text-stone-600">{r.eui_kwh_m2_yr.toFixed(0)}</td>
                  <td className="px-4 py-3 text-stone-600">{r.embodied_carbon_kg_co2e_m2.toFixed(0)}</td>
                  <td className="px-4 py-3 text-stone-600">${r.lifecycle_cost_30yr.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Signal({ label, value, percent }: { label: string; value: string; percent: number }) {
  return (
    <div>
      <div className="flex items-center justify-between gap-4 text-xs">
        <span className="font-medium text-stone-300">{label}</span>
        <span className="font-semibold text-white">{value}</span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-white/10">
        <div className="h-2 rounded-full bg-emerald-300" style={{ width: `${Math.round(percent)}%` }} />
      </div>
    </div>
  );
}
