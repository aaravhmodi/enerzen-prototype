"use client";

import InfoTooltip from "@/components/InfoTooltip";

// Opens the vector plan on its own so it can be zoomed, e.g. on a phone.
function openPlan(svg: string) {
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  window.open(url, "_blank", "noopener");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export type PlanStat = { label: string; value: string; tip?: string; tone?: "good" | "warn" };

export default function MultiSitePlanView({
  svg,
  eyebrow,
  title,
  stats,
  conceptRenderB64,
}: {
  svg: string;
  eyebrow: string;
  title: string;
  stats: PlanStat[];
  conceptRenderB64: string | null;
}) {
  return (
    <section className="site-plan-card">
      <header className="site-plan-header">
        <div>
          <p className="micro-label">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </header>

      <div className="site-plan-body">
        <div>
          {/* Keyed by svg so a new plan replays the layer animation. */}
          <div key={svg} className="site-canvas" dangerouslySetInnerHTML={{ __html: svg }} />
          <p className="site-plan-caption">
            Drawn to scale from the placement engine. Walkway, parking and shared green are concept layers.
          </p>
          <button type="button" className="site-plan-open" onClick={() => openPlan(svg)}>Open full-size plan ↗</button>
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
            {stats.map((stat) => (
              <div key={stat.label}>
                <dt>
                  {stat.label}
                  {stat.tip && <InfoTooltip text={stat.tip} />}
                </dt>
                <dd className={stat.tone === "good" ? "is-good" : stat.tone === "warn" ? "is-warn" : undefined}>
                  {stat.value}
                </dd>
              </div>
            ))}
          </dl>
        </aside>
      </div>
    </section>
  );
}
