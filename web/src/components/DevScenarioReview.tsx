"use client";

import type { CSSProperties } from "react";
import type { DevScenario, ExcludedType } from "@/lib/api";
import { fmtArea, fmtCad } from "@/lib/units";
import InfoTooltip from "@/components/InfoTooltip";

/** Flowchart Path B, "present to user": site plan scenarios before performance optimization. */
export default function DevScenarioReview({
  scenarios,
  selectedIndex,
  approved,
  excluded = [],
  onSelect,
  onToggle,
}: {
  scenarios: DevScenario[];
  excluded?: ExcludedType[];
  selectedIndex: number;
  approved: boolean[];
  onSelect: (index: number) => void;
  onToggle: (index: number) => void;
}) {
  return (
    <section className="scenario-list">
      <header className="scenario-list-header">
        <div>
          <p className="micro-label">Site plan scenarios</p>
          <h2>
            {scenarios.length} housing mix{scenarios.length === 1 ? "" : "es"} fit the land.
          </h2>
          <p>
            Open a scenario to see its plan. Tick the ones to carry into building performance optimization.
          </p>
        </div>
        <span className="scenario-col-note">
          From cost
          <InfoTooltip text="The cheapest catalog configuration for each home, before performance optimization. It is a floor: optimized costs are higher, and the final budget check happens after you approve." />
        </span>
      </header>
      <ol>
        {scenarios.map((scenario, i) => (
          <li
            key={scenario.mix_label}
            className={`scenario-row reveal-row ${i === selectedIndex ? "is-selected" : ""}`}
            style={{ "--n": i } as CSSProperties}
          >
            <label className="scenario-check">
              <input
                type="checkbox"
                checked={approved[i] ?? false}
                onChange={() => onToggle(i)}
                aria-label={`Carry ${scenario.mix_label} forward`}
              />
            </label>
            <button type="button" className="scenario-main" onClick={() => onSelect(i)} aria-pressed={i === selectedIndex}>
              <span className="scenario-name">{scenario.mix_label}</span>
              <span className="scenario-meta">
                {scenario.dwellings} home{scenario.dwellings === 1 ? "" : "s"} · {fmtArea(scenario.total_floor_area_m2)} ·{" "}
                {Math.round(scenario.site_coverage * 100)}% coverage
              </span>
              <span className="scenario-cost">{fmtCad(scenario.screening_cost)}</span>
            </button>
          </li>
        ))}
      </ol>
      {excluded.length > 0 && (
        <div className="scenario-excluded">
          <p className="micro-label">Ruled out by the brief</p>
          <ul>
            {excluded.map((type) => (
              <li key={type.id}>{type.reason}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
