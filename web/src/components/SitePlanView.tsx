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
    <div className="panel overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-stone-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="eyebrow">Site fit</p>
          <h3 className="mt-1 text-xl font-semibold text-stone-950">Placement and solar exposure</h3>
        </div>
        {conceptRenderB64 && (
          <button
            onClick={() => setShowConcept((v) => !v)}
            className="rounded-lg border border-stone-200 bg-white px-4 py-2 text-xs font-semibold text-stone-700 shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-200 hover:text-emerald-800"
          >
            {showConcept ? "Technical diagram" : "Concept illustration"}
          </button>
        )}
      </div>

      <div className="grid gap-0 lg:grid-cols-[1fr_260px]">
        <div className="bg-white p-5">
          {showConcept && conceptRenderB64 ? (
            <div>
              <img
                src={`data:image/png;base64,${conceptRenderB64}`}
                alt="AI-generated concept illustration of the site plan"
                className="w-full rounded-xl border border-stone-200 shadow-sm"
              />
              <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                Concept illustration only - not to scale or authoritative. Use the technical diagram for dimensions.
              </p>
            </div>
          ) : (
            <div
              className="rounded-xl border border-stone-200 bg-stone-50 p-4 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
              dangerouslySetInnerHTML={{ __html: svg }}
            />
          )}
        </div>

        <aside className="border-t border-stone-200 bg-stone-50/80 p-5 lg:border-l lg:border-t-0">
          <dl className="grid gap-3 text-xs text-stone-600">
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
          {layout.notes.length > 0 && (
            <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">
              {layout.notes[0]}
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}

function Stat({ label, value, ok, tip }: { label: string; value: string; ok?: boolean; tip?: string }) {
  const valueColor = ok === undefined ? "text-stone-950" : ok ? "text-emerald-700" : "text-red-600";

  return (
    <div className="tile p-3">
      <dt className="flex items-center gap-1.5 tile-label">
        {label}
        {tip && <InfoTooltip text={tip} />}
      </dt>
      <dd className={`mt-1.5 text-base font-semibold ${valueColor}`}>{value}</dd>
    </div>
  );
}
