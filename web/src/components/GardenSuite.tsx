"use client";

import { docUrl, type AdditionalUnits } from "@/lib/zoning";

const m = (v: number | null | undefined, unit = "m") => (v == null ? null : `${v.toLocaleString()} ${unit}`);

// Garden suite verdict first; the by-law figures only when the zone permits one.
export default function GardenSuite({ aru }: { aru: AdditionalUnits }) {
  const src = (c: AdditionalUnits["section"], what: string) =>
    c.file && c.page ? (
      <a href={docUrl(c.file, c.page)} target="_blank" rel="noreferrer" className="zr-source">
        {what}, p. {c.page}
      </a>
    ) : null;
  if (!aru.permitted_in_zone)
    return <p className="zr-bad">Zone {aru.zone} does not permit additional dwelling units ({src(aru.zone_table, "use table")}).</p>;
  const ok = aru.blockers.length === 0;
  const rows: [string, string | null][] = [
    ["Max height", m(aru.max_height_m)],
    ["Min side and rear yard", aru.min_interior_side_m != null
      ? `${m(aru.min_interior_side_m)} (${m(aru.min_side_rear_if_taller_m)} if over ${m(aru.taller_than_m)} tall)` : null],
    ["Max floor area", aru.max_floor_area_m2 != null
      ? `${m(aru.max_floor_area_m2, "m²")}, and no more than ${aru.max_share_of_house_pct}% of the house` : null],
    ["Footprint left under coverage", aru.footprint_left_m2 != null
      ? `${m(Math.round(aru.footprint_left_m2), "m²")} (${aru.coverage_pct}% of the lot)` : null],
  ];
  return (
    <div>
      <p className={ok ? "zr-ok" : "zr-bad"}>
        {ok ? "A garden suite is permitted here" : "A garden suite is not permitted as the lot stands"} (
        {src(aru.section, `s. ${aru.section.number}`)})
      </p>
      {aru.blockers.map((b) => <p key={b} className="zr-bad">{b}</p>)}
      {aru.checks.map((c) => <p key={c} className="zr-muted">{c}</p>)}
      {ok && (
        <dl className="zr-standards">
          {rows.filter(([, v]) => v).map(([k, v]) => (
            <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
          ))}
        </dl>
      )}
      {!!aru.existing_units && <p className="zr-muted">The City already lists {aru.existing_units} additional unit(s) on this lot.</p>}
    </div>
  );
}
