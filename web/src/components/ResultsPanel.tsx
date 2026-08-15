import type { ConfigResult } from "@/lib/api";

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-3">
      <div className="text-xs text-neutral-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-neutral-900">{value}</div>
    </div>
  );
}

export default function ResultsPanel({ results }: { results: ConfigResult[] }) {
  const top = results[0];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Construction cost" value={`$${top.construction_cost.toLocaleString()}`} />
        <Metric label="Build schedule" value={`${top.construction_weeks.toFixed(1)} wk`} />
        <Metric label="EUI" value={`${top.eui_kwh_m2_yr.toFixed(0)} kWh/m²/yr`} />
        <Metric label="NZR probability" value={`${(top.nzr_probability * 100).toFixed(0)}%`} />
        <Metric label="Embodied carbon" value={`${top.embodied_carbon_kg_co2e_m2.toFixed(0)} kgCO2e/m²`} />
        <Metric label="Avg. monthly utility" value={`$${top.avg_monthly_utility.toFixed(0)}`} />
        <Metric label="30-yr lifecycle cost" value={`$${top.lifecycle_cost_30yr.toLocaleString()}`} />
        <Metric label="Net zero" value={top.net_zero ? "Yes" : "No"} />
      </div>

      <div className="overflow-x-auto rounded-lg border border-neutral-200">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-neutral-50 text-neutral-500">
            <tr>
              <th className="px-3 py-2">Wall</th>
              <th className="px-3 py-2">Roof</th>
              <th className="px-3 py-2">Cost</th>
              <th className="px-3 py-2">Weeks</th>
              <th className="px-3 py-2">EUI</th>
              <th className="px-3 py-2">Carbon</th>
              <th className="px-3 py-2">30yr LCC</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-100">
            {results.slice(0, 20).map((r, i) => (
              <tr key={i} className={i === 0 ? "bg-emerald-50/50" : undefined}>
                <td className="px-3 py-2">{r.wall_id}</td>
                <td className="px-3 py-2">{r.roof_id}</td>
                <td className="px-3 py-2">${r.construction_cost.toLocaleString()}</td>
                <td className="px-3 py-2">{r.construction_weeks.toFixed(1)}</td>
                <td className="px-3 py-2">{r.eui_kwh_m2_yr.toFixed(0)}</td>
                <td className="px-3 py-2">{r.embodied_carbon_kg_co2e_m2.toFixed(0)}</td>
                <td className="px-3 py-2">${r.lifecycle_cost_30yr.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
