"use client";

import type { DevCharges as Charges } from "@/lib/zoning";

const $ = (v: number) => `$${Math.round(v).toLocaleString()}`;

// One total for a new house; each authority's services only when opened.
export default function DevCharges({ dc, gardenSuite }: { dc: Charges; gardenSuite: boolean }) {
  return (
    <div>
      <details>
        <summary>
          Development charges on a new house: <strong>{$(dc.total)}</strong>
        </summary>
        <dl className="zr-standards">
          {dc.lines.map((l) => (
            <div key={l.authority + (l.area ?? "")}>
              <dt>
                <a href={l.url} target="_blank" rel="noreferrer" className="zr-source">
                  {l.authority}
                </a>
                {l.effective && <span className="zr-muted"> from {l.effective}</span>}
              </dt>
              <dd title={Object.entries(l.services).map(([k, v]) => `${k}: ${$(v)}`).join("\n")}>{$(l.amount)}</dd>
            </div>
          ))}
        </dl>
      </details>
      {gardenSuite && (
        <p className="zr-muted">
          A garden suite pays no City or Region charges ({dc.garden_suite.basis})
          {dc.garden_suite.school_boards != null &&
            `; the school boards' ${$(dc.garden_suite.school_boards)} may still apply, so confirm with them`}
          .
        </p>
      )}
    </div>
  );
}
