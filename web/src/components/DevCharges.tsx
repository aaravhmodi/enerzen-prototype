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
      {dc.other && (
        <details>
          <summary>Other charges and application fees</summary>
          <dl className="zr-standards">
            {([["Community benefits charge", dc.other.community_benefits], ["Parkland", dc.other.parkland]] as const).map(
              ([name, c]) => (
                <div key={name}>
                  <dt>
                    <a href={c.url} target="_blank" rel="noreferrer" className="zr-source">{name}</a>
                  </dt>
                  <dd>{c.rule} <span className="zr-muted">({c.source})</span></dd>
                </div>
              ),
            )}
            {dc.other.application_fees.items.map((f) => (
              <div key={f.name}>
                <dt>
                  <a href={dc.other!.application_fees.url} target="_blank" rel="noreferrer" className="zr-source">
                    {f.name}
                  </a>
                </dt>
                <dd>
                  {$(f.base)}
                  {f.per_home && ` + ${f.per_home.map(([n, r]) => `${$(r)}/home for the next ${n}`).join(", ")}`}
                </dd>
              </div>
            ))}
          </dl>
          <p className="zr-muted">
            City fees from {dc.other.application_fees.effective}. {dc.other.application_fees.note}
          </p>
        </details>
      )}
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
