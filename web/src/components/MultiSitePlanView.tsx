"use client";

import type { DevMixResult } from "@/lib/api";
import { fmtEui, fmtArea, fmtCad } from "@/lib/units";
import InfoTooltip from "@/components/InfoTooltip";

const ARCHETYPE_LABELS: Record<string, string> = {
  garden_suite: "Garden Suite",
  three_bhk: "3-Bedroom Unit",
  murb: "MURB",
  townhouse: "Townhouse",
};

export default function MultiSitePlanView({
  svg,
  mix,
  conceptRenderB64,
}: {
  svg: string;
  mix: DevMixResult;
  conceptRenderB64: string | null;
}) {
  const allNzr = mix.nzr_unit_count === mix.total_units;
  return (
    <section className="site-plan-card">
      <header className="site-plan-header">
        <div>
          <p className="micro-label">2D site plan · concept</p>
          <h2>{mix.mix_label}</h2>
        </div>
      </header>

      <div className="site-plan-body">
        <div>
          {/* Keyed by svg so a new plan replays the layer animation. */}
          <div key={svg} className="site-canvas" dangerouslySetInnerHTML={{ __html: svg }} />
          <p className="site-plan-caption">
            Drawn to scale from the placement engine. Walkway, parking and shared green are concept layers.
          </p>
          {conceptRenderB64 && (
            <figure className="site-render">
              <p className="micro-label">AI presentation render</p>
              <img
                src={`data:image/png;base64,${conceptRenderB64}`}
                alt="AI-rendered presentation view of the verified development site plan"
              />
              <figcaption>Visual treatment only. The vector plan above remains the authoritative geometry.</figcaption>
            </figure>
          )}
        </div>

        <aside className="site-plan-stats">
          <dl>
            {Object.entries(mix.units).map(([id, count]) =>
              count > 0 ? (
                <div key={id}>
                  <dt>{ARCHETYPE_LABELS[id] ?? id}</dt>
                  <dd>{count}</dd>
                </div>
              ) : null,
            )}
            <div>
              <dt>Total units</dt>
              <dd>{mix.total_units}</dd>
            </div>
            <div>
              <dt>Built area</dt>
              <dd>{fmtArea(mix.total_floor_area_m2)}</dd>
            </div>
            <div>
              <dt>
                Avg EUI
                <InfoTooltip text="Average Energy Use Intensity across all units in this mix. Lower means less energy consumed per m² each year." />
              </dt>
              <dd>{fmtEui(mix.avg_eui_kwh_m2_yr)}</dd>
            </div>
            <div>
              <dt>
                NZR compliant
                <InfoTooltip text="How many units in this mix meet the Net Zero Ready envelope threshold, out of the total." />
              </dt>
              <dd className={allNzr ? "is-good" : "is-warn"}>
                {mix.nzr_unit_count}/{mix.total_units} units
              </dd>
            </div>
            <div>
              <dt>Avg monthly utility</dt>
              <dd>{fmtCad(mix.avg_monthly_utility)}/unit</dd>
            </div>
          </dl>
        </aside>
      </div>
    </section>
  );
}
