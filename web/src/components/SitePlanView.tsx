"use client";

import { useState } from "react";
import type { SiteLayout } from "@/lib/api";
import InfoTooltip from "@/components/InfoTooltip";

export default function SitePlanView({
  svg,
  layout,
  conceptRenderB64,
}: {
  svg: string;
  layout: SiteLayout;
  conceptRenderB64: string | null;
}) {
  const [showConcept, setShowConcept] = useState(false);

  return (
    <section className="site-plan-card">
      <header className="site-plan-header">
        <div>
          <p className="micro-label">Site fit</p>
          <h2>Placement and solar exposure</h2>
        </div>
        {conceptRenderB64 && (
          <button className="secondary-button" onClick={() => setShowConcept((v) => !v)}>
            {showConcept ? "Technical plan" : "Concept illustration"}
          </button>
        )}
      </header>

      <div className="site-plan-body">
        <div>
          {showConcept && conceptRenderB64 ? (
            <figure className="site-render">
              <img
                src={`data:image/png;base64,${conceptRenderB64}`}
                alt="AI-generated concept illustration of the site plan"
              />
              <figcaption>
                Concept illustration only, not to scale or authoritative. Use the technical plan for dimensions.
              </figcaption>
            </figure>
          ) : (
            <>
              <div key={svg} className="site-canvas" dangerouslySetInnerHTML={{ __html: svg }} />
              <p className="site-plan-caption">Drawn to scale from the placement engine.</p>
            </>
          )}
        </div>

        <aside className="site-plan-stats">
          <dl>
            <Stat
              label="Solar score"
              value={layout.solar_score.toFixed(2)}
              tip="0-1 scale of how well the building's orientation captures passive solar gain. South-facing scores near 1.0; north-facing scores lowest."
            />
            <Stat
              label="Fits on lot"
              value={layout.fits_on_lot ? "Yes" : "No"}
              ok={layout.fits_on_lot}
              tip="Whether the building footprint fits inside the buildable envelope (lot minus setbacks) without overflow."
            />
            <Stat
              label="Setbacks"
              value={layout.setbacks_ok ? "OK" : "Violated"}
              ok={layout.setbacks_ok}
              tip="Whether the placement respects the front/side/rear setback distances you entered."
            />
            <Stat
              label="Orientation"
              value={layout.orientation}
              tip="The direction the building's main facade faces, as placed on this lot."
            />
          </dl>
          {layout.notes.length > 0 && <p className="site-plan-note">{layout.notes[0]}</p>}
        </aside>
      </div>
    </section>
  );
}

function Stat({ label, value, ok, tip }: { label: string; value: string; ok?: boolean; tip?: string }) {
  return (
    <div>
      <dt>
        {label}
        {tip && <InfoTooltip text={tip} />}
      </dt>
      <dd className={ok === undefined ? undefined : ok ? "is-good" : "is-warn"}>{value}</dd>
    </div>
  );
}
