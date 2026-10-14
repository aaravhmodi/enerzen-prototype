"use client";

import { docUrl, type LotStandards } from "@/lib/zoning";

const NAMES: Record<string, string> = {
  front_yard: "Front yard",
  rear_yard: "Rear yard",
  interior_side_yard: "Interior side yard",
  exterior_side_yard: "Exterior side yard",
  lot_frontage: "Minimum frontage",
  lot_area: "Minimum lot area",
  lot_coverage: "Maximum coverage",
  building_height: "Maximum height",
  landscaped_area: "Landscaped area",
  dwelling_depth: "Dwelling depth",
  garage_projection: "Garage projection",
};
const SIDE_NAMES: Record<string, string> = { N: "North", E: "East", S: "South", W: "West" };

const UNIT: Record<string, string> = { "%": "%", m2: " m²", m: " m", ha: " ha", storeys: " storeys" };
const fmt = (value: number | null | undefined, unit?: string | null) =>
  value == null
    ? "—"
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${UNIT[unit ?? "m"] ?? ` ${unit}`}`;

// The lot as a square with each side's setback written on it; the street side is drawn as a road.
function Diagram({ lot }: { lot: LotStandards }) {
  const side = lot.setbacks_by_side;
  const label = (s: string) => {
    const entry = side[s];
    return entry ? `${NAMES[entry.applies]?.replace(" yard", "") ?? entry.applies} ${fmt(entry.value, entry.unit)}` : "";
  };
  const isStreet = (s: string) => s === lot.street_side || s === lot.flank_side;
  return (
    <svg viewBox="0 0 240 240" className="zr-lot-diagram" role="img" aria-label="Setbacks on each side of the lot">
      {isStreet("N") && <rect x="30" y="2" width="180" height="12" className="zr-road" />}
      {isStreet("S") && <rect x="30" y="226" width="180" height="12" className="zr-road" />}
      {isStreet("E") && <rect x="226" y="30" width="12" height="180" className="zr-road" />}
      {isStreet("W") && <rect x="2" y="30" width="12" height="180" className="zr-road" />}
      <rect x="30" y="30" width="180" height="180" className="zr-lot" />
      {lot.buildable_area_m2 != null && <rect x="62" y="62" width="116" height="116" className="zr-envelope" />}
      <text x="120" y="48" textAnchor="middle">{label("N")}</text>
      <text x="120" y="200" textAnchor="middle">{label("S")}</text>
      <text x="196" y="120" textAnchor="middle" transform="rotate(90 196 120)">{label("E")}</text>
      <text x="44" y="120" textAnchor="middle" transform="rotate(-90 44 120)">{label("W")}</text>
      <text x="120" y="124" textAnchor="middle" className="zr-envelope-label">
        {lot.buildable_area_m2 != null ? "Buildable area" : ""}
      </text>
    </svg>
  );
}

export default function LotSetbacks({ lot }: { lot: LotStandards }) {
  const sides = Object.entries(lot.setbacks_by_side);
  const standards = Object.entries(lot.standards).filter(([k]) => !k.endsWith("_yard"));
  if (!lot.zone) {
    return <p className="zr-muted">No zone covers this lot in the City data, so no setbacks apply from the by-law.</p>;
  }
  return (
    <div className="zr-setbacks">
      <div className="zr-setbacks-head">
        <p className="tile-label">
          Setbacks for this lot · Zone {lot.zone_code ?? lot.zone}
          {lot.corner_lot ? " · corner lot" : ""}
          {lot.through_lot ? " · through lot" : ""}
        </p>
        <span className={lot.complete ? "zr-ok" : "zr-bad"}>
          {lot.complete
            ? "Every setback from the by-law"
            : lot.basis === "figure"
              ? "Setbacks are drawn on a figure in the by-law"
              : "Some setbacks not found in the by-law"}
        </span>
      </div>
      {lot.basis_note && (
        <p className="zr-muted">
          {lot.basis === "figure" ? "The by-law says: " : ""}
          {lot.basis_note}
          {lot.basis_page ? ` (${lot.basis_document ?? "by-law"}, page ${lot.basis_page})` : ""}
        </p>
      )}
      {lot.figure_setbacks?.map((f) => (
        <div key={`${f.exception}-${f.page}-${f.applies_to ?? ""}`} className="zr-muted">
          <p>
            Read from {f.figure}
            {f.applies_to ? `, ${f.applies_to}` : ""} ({f.document}, page {f.page}):{" "}
            {f.setbacks.map((s) => `${fmt(s.value_m, "m")} from ${s.from}`).join("; ")}
            {f.setbacks.some((s) => s.stated.endsWith("ft")) ? " (drawn in feet)" : ""}.
          </p>
          {f.note && <p>{f.note}</p>}
        </div>
      ))}
      {lot.figure_setbacks && lot.figure_setbacks.length > 0 && (
        <p className="zr-muted">These distances were read by eye from the drawing; check the figure before relying on one.</p>
      )}
      {sides.length > 0 ? (
        <div className="zr-setbacks-body">
          <Diagram lot={lot} />
          <table className="zr-table">
            <thead>
              <tr>
                <th>Side</th>
                <th>Standard</th>
                <th>Minimum</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {sides.map(([s, entry]) => (
                <tr key={s}>
                  <td>
                    {SIDE_NAMES[s]}
                    {s === lot.street_side ? " (street)" : s === lot.flank_side ? " (flank street)" : ""}
                  </td>
                  <td>{NAMES[entry.applies] ?? entry.applies}</td>
                  <td>{fmt(entry.value, entry.unit)}</td>
                  <td>
                    {entry.file && entry.page ? (
                      <a href={docUrl(entry.file, entry.page)} target="_blank" rel="noreferrer">
                        {entry.from}, p. {entry.page}
                      </a>
                    ) : (
                      <span className="zr-bad">Not in the stored by-law</span>
                    )}
                    {entry.note && <small className="zr-muted"> {entry.note}</small>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="zr-muted">No road is mapped near this lot, so its front, rear and sides can&apos;t be told apart.</p>
      )}
      {standards.length > 0 && (
        <dl className="zr-facts">
          {standards.map(([key, rule]) => (
            <div key={key}>
              <dt>{NAMES[key] ?? key}</dt>
              <dd>
                {fmt(rule.value, rule.unit)}{" "}
                {rule.file && rule.page && (
                  <a href={docUrl(rule.file, rule.page)} target="_blank" rel="noreferrer" className="zr-source">
                    {rule.from}, p. {rule.page}
                  </a>
                )}
              </dd>
            </div>
          ))}
          {lot.buildable_area_m2 != null && (
            <div>
              <dt>Buildable area inside setbacks</dt>
              <dd>{Math.round(lot.buildable_area_m2).toLocaleString()} m²</dd>
            </div>
          )}
          {lot.max_coverage_m2 != null && (
            <div>
              <dt>Coverage allows</dt>
              <dd>{Math.round(lot.max_coverage_m2).toLocaleString()} m² footprint</dd>
            </div>
          )}
        </dl>
      )}
      {lot.lot_checks.map((check) => (
        <p key={check.standard} className={check.ok ? "zr-ok" : "zr-bad"}>
          {NAMES[check.standard]}: lot has {fmt(check.lot, check.standard === "lot_area" ? "m2" : "m")}, zone
          requires {fmt(check.required, check.standard === "lot_area" ? "m2" : "m")}
          {check.ok ? " (meets it)" : " (below it: the lot is legal non-complying or needs relief)"}
        </p>
      ))}
      {lot.missing.length > 0 && (
        <p className="zr-muted">
          Not found in the stored by-law for this zone: {lot.missing.map((m) => NAMES[m] ?? m).join(", ")}.
        </p>
      )}
      {Object.entries(lot.not_regulated ?? {}).map(([key, note]) => (
        <p key={key} className="zr-muted">
          {NAMES[key] ?? key}: {note}
        </p>
      ))}
      {lot.exceptions_without_text.length > 0 && (
        <p className="zr-bad">
          Exception {lot.exceptions_without_text.join(", ")} applies to this lot but its section isn&apos;t stored, so
          its changes to these setbacks are not shown.
        </p>
      )}
      {lot.approximate && (
        <p className="zr-muted">The lot is irregular; sides are read from its bounding rectangle.</p>
      )}
    </div>
  );
}
