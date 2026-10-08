"use client";

import type { DevMixResult } from "@/lib/api";
import { fmtArea, fmtCad, fmtCarbon, fmtEui } from "@/lib/units";
import InfoTooltip from "@/components/InfoTooltip";

const TYPE_NAMES: Record<string, string> = {
  garden_suite: "Garden Suite",
  three_bhk: "3-Bedroom Unit",
  murb: "MURB",
  townhouse: "Townhouse",
};

/** Flowchart Path B steps 6-7: development calculations for the recommended scenario. */
export default function DevRecommendation({ mix, softFraction }: { mix: DevMixResult; softFraction: number }) {
  const tiles: { label: string; value: string; tip: string }[] = [
    { label: "Homes", value: String(mix.total_units), tip: "Dwellings in this scenario. A MURB counts all of its units." },
    { label: "Built area", value: fmtArea(mix.total_floor_area_m2), tip: "Total conditioned floor area across all homes." },
    { label: "Hard cost", value: fmtCad(mix.total_cost), tip: "Optimized construction cost for every home, Class D." },
    {
      label: "Soft costs",
      value: fmtCad(mix.soft_cost),
      tip: `Default allowance of ${Math.round(softFraction * 100)}% of hard cost for consultants, permits and development charges, legal, insurance and financing.`,
    },
    { label: "Total project cost", value: fmtCad(mix.total_project_cost), tip: "Hard cost plus soft costs. A Class D feasibility estimate, not a quotation." },
    {
      label: "Pre-construction",
      value: `${mix.soft_timeline_weeks} wk`,
      tip: "Design and engineering, site plan approval (exempt for 10 or fewer homes) and building permit review, assuming complete applications and no rezoning.",
    },
    {
      label: "Fabrication to close",
      value: `${mix.construction_weeks} wk`,
      tip: "Factory fabrication and site work to envelope close for every home, produced in sequence.",
    },
    { label: "Avg EUI", value: fmtEui(mix.avg_eui_kwh_m2_yr), tip: "Floor-area-weighted energy use intensity across the homes." },
    { label: "Embodied carbon", value: fmtCarbon(mix.avg_carbon_kg_co2e_m2), tip: "Floor-area-weighted embodied carbon of the optimized assemblies." },
    {
      label: "30-yr lifecycle carbon",
      value: fmtCarbon(mix.lifecycle_carbon_30yr_kg_co2e_m2),
      tip: "Embodied plus 30 years of operational carbon, floor-area weighted.",
    },
    { label: "30-yr lifecycle cost", value: fmtCad(mix.lifecycle_cost_30yr), tip: "Construction plus 30 years of discounted energy costs, all homes." },
    {
      label: "Net Zero Ready homes",
      value: `${mix.nzr_unit_count}/${mix.total_units}`,
      tip: "Homes whose optimized envelope meets the Net Zero Ready threshold.",
    },
  ];
  return (
    <section className="dev-recommendation reveal-hero">
      <header>
        <p className="micro-label">Recommended community</p>
        <h2>{mix.mix_label}</h2>
        <ul className="dev-systems">
          {Object.entries(mix.configurations).map(([type, systems]) => (
            <li key={type}>
              <strong>{TYPE_NAMES[type] ?? type}</strong> {systems}
            </li>
          ))}
        </ul>
      </header>
      <div className="dev-tiles reveal-tiles">
        {tiles.map((tile) => (
          <div key={tile.label} className="dev-tile">
            <span>
              {tile.label}
              <InfoTooltip text={tile.tip} />
            </span>
            <strong>{tile.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}
