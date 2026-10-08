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
type ExploringPath = "single" | "dev-scenarios" | "dev-performance";

function stagesFor(path: ExploringPath, c: ExploringContext): Stage[] {
  if (path === "single") {
    return [
      { title: "Reading your brief", how: `${c.brief}. Budget and the ${c.target} target become hard constraints; your weights stay soft priorities.` },
      { title: "Site and regulatory context", how: `Loading ${c.place} climate, degree-days, snow load and regional energy rates. Zoning is not checked until a parcel is selected.` },
      { title: "Setting the design geometry", how: "Taking the catalog design you chose, or your custom footprint, as the starting geometry for every configuration." },
      { title: "Configuring building systems", how: "Combining wall, roof and foundation assemblies across insulation thicknesses with windows, mechanical and solar options." },
      { title: "Calculating performance", how: "Effective R-values, heat loss, EUI and TEDI, then cost, build weeks, embodied and lifecycle carbon for every configuration." },
      { title: "Applying the performance gate", how: `Setting aside configurations that exceed your budget or miss the ${c.target} threshold.` },
      { title: "Ranking the trade-offs", how: "Pareto-ranking what passed, then weighting cost, energy, carbon and speed by your priorities." },
      { title: "Placing it on the site", how: `Fitting the footprint inside the setbacks on ${c.site} and turning its long face toward the sun.` },
    ];
  }
  if (path === "dev-scenarios") {
    return [
      { title: "Reading the development brief", how: `${c.brief}. Budget and the ${c.target} target are hard constraints.` },
      { title: "Land and planning context", how: `${c.site}. ${c.place} city-wide data is loaded; zoning is not checked until a parcel is selected.` },
      { title: "Selecting housing types", how: "Taking the catalog types you allowed, with their footprints, storeys and homes per building." },
      { title: "Pricing a cost floor", how: "Costing the cheapest catalog configuration of each type, so mixes that could never meet the budget are set aside early." },
      { title: "Testing housing mixes", how: "Enumerating combinations of the selected types within the buildable area and the budget." },
      { title: "Fitting mixes on the land", how: "Placing buildings in bands around a shared walkway. Mixes that do not fit inside the setbacks are set aside." },
      { title: "Drawing the 2D site plan", how: "Walkway, street-facing entrances, parking and the shared rear garden for the leading scenario." },
    ];
  }
  return [
    { title: "Reading the approved scenarios", how: "Carrying forward only the site plans you approved." },
    { title: "Optimizing building performance", how: "Running each housing type through the envelope, window and mechanical options to find its best configuration." },
    { title: "Applying the performance gate", how: `Setting aside configurations that miss the ${c.target} threshold or the budget.` },
    { title: "Development calculations", how: "Hard and soft costs, pre-construction and fabrication time, energy, embodied and lifecycle carbon, lifecycle cost and yield for each scenario." },
    { title: "Ranking scenarios", how: "Weighting yield, cost, energy and carbon by your priorities." },
    { title: "Preparing the recommendation", how: "Drawing the recommended community's site plan and, when available, its presentation render." },
  ];
}

const STEP_MS = 1500;

export default function ExploringStage({
  path,
  context,
}: {
  path: ExploringPath;
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
