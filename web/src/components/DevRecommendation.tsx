"use client";

import type { DevMixResult, RentalProForma } from "@/lib/api";
import { fmtCad, useUnits } from "@/lib/units";
import InfoTooltip from "@/components/InfoTooltip";

const TYPE_NAMES: Record<string, string> = {
  garden_suite: "Garden Suite",
  three_bhk: "3-Bedroom Unit",
  murb: "MURB",
  townhouse: "Townhouse",
};

/** Flowchart Path B steps 6-7: development calculations for the recommended scenario. */
export default function DevRecommendation({ mix, softFraction }: { mix: DevMixResult; softFraction: number }) {
  const u = useUnits();
  const tiles: { label: string; value: string; tip: string }[] = [
    { label: "Homes", value: String(mix.total_units), tip: "Dwellings in this scenario. A MURB counts all of its units." },
    { label: "Built area", value: u.area(mix.total_floor_area_m2), tip: "Total conditioned floor area across all homes." },
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
    { label: "Avg EUI", value: u.eui(mix.avg_eui_kwh_m2_yr), tip: "Floor-area-weighted energy use intensity across the homes." },
    { label: "Embodied carbon", value: u.carbon(mix.avg_carbon_kg_co2e_m2), tip: "Floor-area-weighted embodied carbon of the optimized assemblies." },
    {
      label: "30-yr lifecycle carbon",
      value: u.carbon(mix.lifecycle_carbon_30yr_kg_co2e_m2),
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
      {mix.rental && <Rental r={mix.rental} />}
    </section>
  );
}

const BEDROOMS = ["Studio", "1-bed", "2-bed", "3-bed+"];

// Market rent from CMHC and the MLI Select terms the community's energy performance reaches.
function Rental({ r }: { r: RentalProForma }) {
  const m = r.mli_select;
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  return (
    <div className="dev-rental">
      <h3>Rent and financing</h3>
      <p>
        At today&apos;s market rents these {r.homes} homes would lease for <strong>{fmtCad(r.monthly_rent)}/month</strong>{" "}
        ({fmtCad(r.annual_effective_rent)}/year after {pct(r.vacancy_rate)} vacancy
        {r.gross_yield_on_cost != null && `, a ${(r.gross_yield_on_cost * 100).toFixed(1)}% gross yield on cost`}). Apartments
        built since 2015 in the Toronto area&apos;s suburbs lease for about {fmtCad(r.new_building_monthly_rent)}/month for the same homes.
      </p>
      <p className="zr-muted">
        {Object.entries(r.rents_used)
          .map(([b, v]) => `${v.homes} × ${BEDROOMS[Number(b)]} at ${fmtCad(v.monthly)} (${v.area})`)
          .join(" · ")}
        . Asking rents of vacant units,{" "}
        <a href={r.url} target="_blank" rel="noreferrer">{r.source}</a>.
      </p>
      {m.eligible ? (
        <p>
          <a href={m.url} target="_blank" rel="noreferrer">CMHC MLI Select</a>: energy use is about{" "}
          {pct(m.energy_better_than_code)} below a code-built home, worth <strong>{m.energy_points} points</strong> if an
          energy model against NBC 2020 Tier 1 confirms it. 50 points allow up to 95% of cost as the loan (
          {fmtCad(m.max_loan_at_50_points)}) over 40 years, 70 points 45 years, and 100 points 50 years with limited
          recourse, at a debt coverage of at least {m.min_dcr.toFixed(2)}. Points can be added by renting{" "}
          {m.affordability_options.map((o) => `${o.homes} homes (${o.points} pts)`).join(", ")} at 30% of median renter
          income for 10 years, or through accessibility ({m.accessibility_options.map((o) => `${o.option}: ${o.points} pts`).join("; ")}).
        </p>
      ) : (
        <p className="zr-muted">MLI Select needs at least 5 rental homes.</p>
      )}
    </div>
  );
}
