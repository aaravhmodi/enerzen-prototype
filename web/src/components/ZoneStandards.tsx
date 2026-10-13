"use client";

import { useState } from "react";
import { docUrl, type Provision } from "@/lib/zoning";

const LABELS: Record<string, string> = {
  permitted_uses: "Permitted uses",
  lot_frontage: "Lot frontage",
  lot_area: "Lot area",
  front_yard: "Front yard",
  side_yard: "Side yards",
  rear_yard: "Rear yard",
  building_height: "Building height",
  lot_coverage: "Lot coverage",
  floor_area: "Floor area",
  landscaping: "Landscaping",
  parking: "Parking and loading",
  dwelling_units: "Dwelling units",
};

const number = (measure: string) => Number(measure.replace(",", ".").match(/\d+(?:\.\d+)?/)?.[0]);
const unit = (measure: string) => measure.replace(/^[\d.,\s]+/, "").trim();

// Only a line with one stated bound and one measure is compared, and only preliminarily.
function verdict(provision: Provision, value: string) {
  const proposed = Number(value);
  if (!value || !Number.isFinite(proposed) || !provision.bound || provision.measures.length !== 1) return null;
  const limit = number(provision.measures[0]);
  if (!Number.isFinite(limit)) return null;
  const ok = provision.bound === "minimum" ? proposed >= limit : proposed <= limit;
  return { ok, text: ok ? "Appears to meet" : provision.bound === "minimum" ? "Below the minimum" : "Above the maximum" };
}

export default function ZoneStandards({ standards }: { standards: Record<string, Provision[]> }) {
  const [proposal, setProposal] = useState<Record<string, string>>({});
  const kinds = Object.entries(standards).filter(([, list]) => list.length);
  if (!kinds.length) {
    return (
      <p className="zr-muted">
        No measured standards were found on by-law pages naming this zone. Search the by-laws for the zone&apos;s
        section.
      </p>
    );
  }
  return (
    <div className="zr-standards">
      <p className="tile-label">What the by-law text says for this zone</p>
      {kinds.map(([kind, list]) => {
        const comparable = list.find((p) => p.bound && p.measures.length === 1);
        const result = comparable ? verdict(comparable, proposal[kind] ?? "") : null;
        return (
          <div key={kind} className="zr-standard">
            <div className="zr-hit-head">
              <span className="zr-standard-name">{LABELS[kind] ?? kind}</span>
              {comparable && (
                <label className="zr-proposal">
                  Yours
                  <input
                    inputMode="decimal"
                    value={proposal[kind] ?? ""}
                    onChange={(e) => setProposal({ ...proposal, [kind]: e.target.value })}
                    aria-label={`Proposed ${LABELS[kind] ?? kind} in ${unit(comparable.measures[0])}`}
                  />
                  <small>{unit(comparable.measures[0])}</small>
                </label>
              )}
            </div>
            {result && <p className={result.ok ? "zr-ok" : "zr-bad"}>{result.text} (preliminary; read the page)</p>}
            <ul>
              {list.map((p) => (
                <li key={`${p.file}-${p.page}-${p.text}`}>
                  {p.text}{" "}
                  <a href={docUrl(p.file, p.page)} target="_blank" rel="noreferrer">
                    p. {p.page}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
