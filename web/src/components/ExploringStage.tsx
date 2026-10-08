"use client";

import { useEffect, useState } from "react";
import Architecture from "@/components/Architecture";

export type ExploringContext = {
  place: string;
  target: string;
  brief: string;
  site: string;
};

type Stage = { title: string; how: string };

// Narrates the engine's real pipeline, in the order it actually runs. The
// stages advance on a timer: the API returns one response, not live progress.
function stagesFor(path: "single" | "development", c: ExploringContext): Stage[] {
  if (path === "single") {
    return [
      { title: "Reading your brief", how: `${c.brief}. Budget and the ${c.target} target become hard constraints; your weights stay soft priorities.` },
      { title: "Site and regulatory context", how: `Loading ${c.place} climate, degree-days, snow load and regional energy rates. Zoning is not checked until a parcel is selected.` },
      { title: "Matching the design catalog", how: "Lining up your floor area, storeys and footprint with EnerZen's catalog designs." },
      { title: "Configuring building systems", how: "Combining wall, roof and foundation assemblies across insulation thicknesses with windows, mechanical and solar options." },
      { title: "Calculating performance", how: "Effective R-values, heat loss, EUI and TEDI, then cost, build weeks, embodied and lifecycle carbon for every configuration." },
      { title: "Applying the performance gate", how: `Setting aside configurations that exceed your budget or miss the ${c.target} threshold.` },
      { title: "Ranking the trade-offs", how: "Pareto-ranking what passed, then weighting cost, energy, carbon and speed by your priorities." },
      { title: "Placing it on the site", how: `Fitting the footprint inside the setbacks on ${c.site} and turning its long face toward the sun.` },
    ];
  }
  return [
    { title: "Reading the development brief", how: `${c.brief}. Budget and the ${c.target} target are hard constraints.` },
    { title: "Land and planning context", how: `${c.site}. ${c.place} city-wide data is loaded; zoning is not checked until a parcel is selected.` },
    { title: "Optimizing each housing type", how: "Running every selected catalog type through the envelope and systems optimizer to find its best configuration." },
    { title: "Sizing the possibilities", how: "Capping each type by buildable area and budget before testing combinations." },
    { title: "Testing housing mixes", how: "Enumerating mixes of the selected types and discarding any that exceed the budget." },
    { title: "Fitting mixes on the land", how: "Placing buildings in bands around a shared walkway. Mixes that do not fit inside the setbacks are set aside." },
    { title: "Development calculations", how: "Totalling cost, unit yield, floor area, average EUI, carbon and utility cost for each feasible mix." },
    { title: "Ranking scenarios", how: "Weighting yield, cost, energy and carbon by your priorities." },
    { title: "Drawing the 2D site plan", how: "Walkway, parking, the shared rear garden and numbered buildings for the leading mix." },
  ];
}

const STEP_MS = 1500;

export default function ExploringStage({
  path,
  context,
}: {
  path: "single" | "development";
  context: ExploringContext;
}) {
  const stages = stagesFor(path, context);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed(Date.now() - started), 250);
    return () => window.clearInterval(timer);
  }, []);
  const current = Math.min(stages.length - 1, Math.floor(elapsed / STEP_MS));
  const lingering = elapsed > stages.length * STEP_MS + 2500;

  return (
    <section className="exploring" role="status" aria-live="polite" aria-label="Exploring your possibilities">
      <div className="exploring-copy">
        <p className="micro-label">
          <span className="status-dot pulse" /> Exploring · {String(current + 1).padStart(2, "0")}
          <span className="muted"> / {String(stages.length).padStart(2, "0")}</span>
        </p>
        <h1 aria-label="Exploring your possibilities.">
          <span className="hero-title-line" aria-hidden="true">
            <span className="word-reveal">Exploring </span>
            <span className="word-reveal" style={{ animationDelay: "80ms" }}>your</span>
          </span>
          <span className="hero-title-line muted-title" aria-hidden="true">
            <span className="word-reveal" style={{ animationDelay: "160ms" }}>possibilities.</span>
          </span>
        </h1>
        <div key={current} className="exploring-now">
          <h2>{stages[current].title}</h2>
          <p>{stages[current].how}</p>
        </div>
        <ol className="exploring-steps" aria-hidden="true">
          {stages.map((stage, index) => (
            <li key={stage.title} className={index < current ? "done" : index === current ? "active" : ""}>
              <span className="exploring-mark">{index < current ? "✓" : ""}</span>
              {stage.title}
            </li>
          ))}
        </ol>
        <p className="exploring-time">
          {Math.floor(elapsed / 1000)}s{lingering ? " · Still working. Larger briefs and concept renders take longer." : ""}
        </p>
      </div>
      <div className="exploring-art" aria-hidden="true">
        <div className="art-topline">
          <span>THE ENGINE AT WORK</span>
          <span>{String(current + 1).padStart(2, "0")} — {stages[current].title.toUpperCase()}</span>
        </div>
        <div className="exploring-scan">
          <Architecture />
        </div>
      </div>
    </section>
  );
}
