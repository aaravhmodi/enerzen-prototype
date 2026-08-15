"use client";

import { useState } from "react";
import type { SiteLayout } from "@/lib/api";

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
    <div className="rounded-xl border border-neutral-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-neutral-800">Site plan</h3>
        {conceptRenderB64 && (
          <button
            onClick={() => setShowConcept((v) => !v)}
            className="rounded-md border border-neutral-300 px-2 py-1 text-xs text-neutral-600 hover:bg-neutral-50"
          >
            {showConcept ? "Show technical diagram" : "Show concept illustration"}
          </button>
        )}
      </div>

      {showConcept && conceptRenderB64 ? (
        <div>
          <img
            src={`data:image/png;base64,${conceptRenderB64}`}
            alt="AI-generated concept illustration of the site plan"
            className="w-full rounded-lg border border-neutral-200"
          />
          <p className="mt-2 text-xs text-amber-700">
            Concept illustration only — not to scale, not authoritative. See the
            technical diagram for accurate dimensions.
          </p>
        </div>
      ) : (
        <div
          className="[&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      )}

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-neutral-600 sm:grid-cols-4">
        <div>
          <dt className="text-neutral-400">Solar score</dt>
          <dd className="font-medium text-neutral-800">{layout.solar_score.toFixed(2)}</dd>
        </div>
        <div>
          <dt className="text-neutral-400">Fits on lot</dt>
          <dd className={`font-medium ${layout.fits_on_lot ? "text-emerald-700" : "text-red-600"}`}>
            {layout.fits_on_lot ? "Yes" : "No"}
          </dd>
        </div>
        <div>
          <dt className="text-neutral-400">Setbacks</dt>
          <dd className={`font-medium ${layout.setbacks_ok ? "text-emerald-700" : "text-red-600"}`}>
            {layout.setbacks_ok ? "OK" : "Violated"}
          </dd>
        </div>
        <div>
          <dt className="text-neutral-400">Orientation</dt>
          <dd className="font-medium text-neutral-800">{layout.orientation}</dd>
        </div>
      </dl>
      {layout.notes.length > 0 && (
        <p className="mt-3 rounded-md bg-amber-50 p-2 text-xs text-amber-800">{layout.notes[0]}</p>
      )}
    </div>
  );
}
