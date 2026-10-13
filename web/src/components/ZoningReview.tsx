"use client";

import { useState } from "react";
import { CATEGORY_LABELS, docUrl, type Hit, type Lookup } from "@/lib/zoning";
import { useUnits } from "@/lib/units";
import ZoneStandards from "./ZoneStandards";
import LotSetbacks from "./LotSetbacks";

const GROUP_LABELS: Record<string, string> = {
  zoning_bylaw: "Zoning by-laws",
  official_plan: "Official Plan",
  provincial: "Provincial (PPS 2024, O. Reg. 545/06, plans)",
  heritage_environment: "Heritage and environment",
  development_standards: "Development standards",
  other: "Other planning pages",
};

// Opens the design workspace on this lot: its point, measured sides and street side.
function workspaceLink(lookup: Lookup) {
  const dims = lookup.steps?.["1_property_identification"].from_city_data?.dimensions;
  const params = new URLSearchParams({ lot: `${lookup.query!.latitude},${lookup.query!.longitude}` });
  if (dims) {
    params.set("w", String(dims.width_m));
    params.set("d", String(dims.depth_m));
    if (dims.street_side) params.set("street", dims.street_side);
  }
  const lot = lookup.steps?.["3_proposed_development"].lot_standards;
  if (lot) {
    const sides = Object.values(lot.setbacks_by_side);
    const pick = (applies: string) => sides.find((v) => v.applies === applies)?.value;
    const front = pick("front_yard");
    const rear = pick("rear_yard");
    // The site planner takes one side setback: the larger of the lot's two.
    const side = Math.max(...sides.filter((v) => v.applies.endsWith("side_yard")).map((v) => v.value ?? 0));
    if (front != null) params.set("front", String(front));
    if (rear != null) params.set("rear", String(rear));
    if (side > 0) params.set("side", String(side));
  }
  return `/?${params}`;
}

function Attributes({ attributes, limit = 8 }: { attributes: Record<string, unknown>; limit?: number }) {
  const [open, setOpen] = useState(false);
  const entries = Object.entries(attributes).filter(([k]) => !k.startsWith("_"));
  if (!entries.length) return null;
  const shown = open ? entries : entries.slice(0, limit);
  return (
    <>
      <dl className="zr-attrs">
        {shown.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{String(v)}</dd>
          </div>
        ))}
      </dl>
      {entries.length > limit && (
        <button type="button" className="zr-more" onClick={() => setOpen(!open)}>
          {open ? "Fewer fields" : `All ${entries.length} fields`}
        </button>
      )}
    </>
  );
}

function Hits({ hits, empty }: { hits: Hit[]; empty: string }) {
  if (!hits.length) return <p className="zr-muted">{empty}</p>;
  return (
    <ul className="zr-hits">
      {hits.map((hit, i) => (
        <li key={`${hit.layer}-${i}`}>
          <div className="zr-hit-head">
            <a href={hit.source_url} target="_blank" rel="noreferrer">
              {hit.layer}
            </a>
            <span>
              {hit.distance_m > 0
                ? `${Math.round(hit.distance_m)} m away`
                : hit.parcel_share_pct != null
                  ? `${hit.parcel_share_pct}% of lot`
                  : "On the lot"}
            </span>
          </div>
          <Attributes attributes={hit.attributes} />
        </li>
      ))}
    </ul>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="section-card zr-step">
      <div className="section-heading">
        <span className="section-badge">{n}</span>
        <h3>{title}</h3>
      </div>
      <div className="zr-step-body">{children}</div>
    </section>
  );
}

function Checklist({ items, label }: { items: string[]; label: string }) {
  return (
    <div className="zr-checklist">
      <p className="tile-label">{label}</p>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export default function ZoningReview({ lookup }: { lookup: Lookup }) {
  const u = useUnits();
  if (!lookup.steps) {
    return (
      <div className="section-card">
        <p className="eyebrow">{lookup.label}</p>
        <p className="zr-muted">{lookup.detail}</p>
      </div>
    );
  }
  const s = lookup.steps;
  const property = s["1_property_identification"].from_city_data;
  const zoning = s["2_existing_zoning_and_official_plan"];
  const site = s["4_site_characteristics"];
  const docs = s["5_supporting_documents"];
  const frameworks = s["6_planning_frameworks"];
  const overlayEntries = Object.entries(zoning.overlays);
  const onLot = overlayEntries.filter(([, hits]) => hits.length);

  return (
    <div className="zr">
      <div className="zr-summary">
        <div className="tile">
          <p className="tile-label">Zone</p>
          <p className="tile-value">{zoning.zone_codes.join(", ") || "Not found"}</p>
        </div>
        <div className="tile">
          <p className="tile-label">By-law</p>
          <p className="tile-value">{zoning.bylaw_numbers.join(", ") || "Not cited"}</p>
        </div>
        <div className="tile">
          <p className="tile-label">Lot area</p>
          <p className="tile-value">{property?.area_m2 ? u.area(property.area_m2) : "No parcel"}</p>
        </div>
        <div className="tile">
          <p className="tile-label">Overlays nearby</p>
          <p className="tile-value">{onLot.length ? onLot.map(([c]) => CATEGORY_LABELS[c] ?? c).join(", ") : "None found"}</p>
        </div>
      </div>
      {lookup.query && (
        <a className="quiet-button zr-use-lot" href={workspaceLink(lookup)}>
          Use this lot in the workspace <span aria-hidden="true">↗</span>
        </a>
      )}
      <p className="zr-disclaimer">
        {lookup.detail} Data retrieved {lookup.retrieved_at?.slice(0, 10)}.
      </p>

      <Step n={1} title="Property identification">
        {property ? (
          <>
            <dl className="zr-facts">
              <div>
                <dt>Address</dt>
                <dd>{property.address || "Not in City data"}</dd>
              </div>
              <div>
                <dt>Roll number</dt>
                <dd>{property.roll_number || "Not in City data"}</dd>
              </div>
              <div>
                <dt>PIN</dt>
                <dd>{property.pin || "Not in City data"}</dd>
              </div>
              <div>
                <dt>Legal description</dt>
                <dd>{property.legal_description || "Not in City data"}</dd>
              </div>
              {property.perimeter_m != null && (
                <div>
                  <dt>Perimeter</dt>
                  <dd>{Math.round(property.perimeter_m)} m</dd>
                </div>
              )}
            </dl>
            {property.note && <p className="zr-muted">{property.note}</p>}
            {property.attributes && <Attributes attributes={property.attributes} limit={4} />}
          </>
        ) : (
          <p className="zr-muted">No parcel in the City data contains this point.</p>
        )}
        <Checklist label="You confirm" items={s["1_property_identification"].applicant_must_confirm} />
      </Step>

      <Step n={2} title="Existing zoning and Official Plan">
        <h4>Zoning</h4>
        <Hits hits={zoning.zoning} empty="No zoning polygon covers this lot in the City data." />
        <h4>Official Plan</h4>
        <Hits hits={zoning.official_plan} empty="No Official Plan designation layer covers this lot." />
        <h4>Overlays</h4>
        {overlayEntries.map(([category, hits]) => (
          <details key={category} open={hits.length > 0} className="zr-overlay">
            <summary>
              {CATEGORY_LABELS[category] ?? category} <span>{hits.length ? `${hits.length} found` : "none nearby"}</span>
            </summary>
            <Hits hits={hits} empty="Nothing within the review distance." />
          </details>
        ))}
        <Checklist label="You supply" items={zoning.applicant_must_supply} />
      </Step>

      <Step n={3} title="Proposed development">
        <LotSetbacks lot={s["3_proposed_development"].lot_standards} />
        <ZoneStandards standards={s["3_proposed_development"].zone_standards_in_bylaw_text} />
        <Checklist label="You supply" items={s["3_proposed_development"].applicant_must_supply} />
        <p className="zr-muted">{s["3_proposed_development"].check_against}</p>
      </Step>

      <Step n={4} title="Site characteristics">
        <h4>Servicing within 60 m</h4>
        <Hits hits={site.servicing_nearby} empty="No servicing layer features nearby in the City data." />
        <h4>Adjacent zoning (within 30 m)</h4>
        <Hits hits={site.adjacent_zoning} empty="No other zone within 30 m in the City data." />
        <h4>Topography</h4>
        <Hits hits={site.topography} empty="No topography layer in the City data here." />
        <Checklist label="You supply" items={site.applicant_must_supply} />
      </Step>

      <Step n={5} title="Supporting documents">
        <Checklist label="Always" items={docs.always} />
        {Object.keys(docs.triggered_by_overlays).length > 0 && (
          <Checklist label="Triggered by this lot's overlays" items={Object.values(docs.triggered_by_overlays)} />
        )}
        <Checklist label="Depending on scale" items={docs.by_scale} />
        <p className="zr-muted">{docs.reference}</p>
      </Step>

      <Step n={6} title="Planning frameworks and by-law references">
        <h4>This lot&apos;s zone in the by-laws</h4>
        {frameworks.zoning_bylaw_references.length ? (
          <ul className="zr-refs">
            {frameworks.zoning_bylaw_references.map((ref) => (
              <li key={ref.file}>
                <div className="zr-hit-head">
                  <a href={docUrl(ref.file)} target="_blank" rel="noreferrer">
                    {ref.title}
                  </a>
                  <a href={ref.url} target="_blank" rel="noreferrer" className="zr-source">
                    City source ↗
                  </a>
                </div>
                {ref.names_parcel_bylaw.length > 0 && (
                  <p className="zr-tag">Names this lot&apos;s by-law {ref.names_parcel_bylaw.join(", ")}</p>
                )}
                {Object.entries(ref.zone_pages).map(([zone, pages]) => (
                  <p key={zone} className="zr-pages">
                    {zone} on page{pages.length > 1 ? "s" : ""}{" "}
                    {pages.map((page, i) => (
                      <span key={page}>
                        {i > 0 && ", "}
                        <a href={docUrl(ref.file, page)} target="_blank" rel="noreferrer">
                          {page}
                        </a>
                      </span>
                    ))}
                  </p>
                ))}
                {ref.excerpts.map((excerpt) => (
                  <blockquote key={`${excerpt.zone}-${excerpt.page}`}>
                    <a href={docUrl(ref.file, excerpt.page)} target="_blank" rel="noreferrer">
                      p. {excerpt.page}
                    </a>{" "}
                    {excerpt.text}
                  </blockquote>
                ))}
              </li>
            ))}
          </ul>
        ) : (
          <p className="zr-muted">No stored by-law mentions this lot&apos;s zone yet. Search the by-laws below.</p>
        )}
        <h4>Council amendments naming this lot</h4>
        {frameworks.council_amendments_naming_this_lot.length ? (
          <ul className="zr-refs">
            {frameworks.council_amendments_naming_this_lot.map((a) => (
              <li key={a.file}>
                <div className="zr-hit-head">
                  <a href={docUrl(a.file)} target="_blank" rel="noreferrer">
                    {a.title}
                  </a>
                  {a.meeting && (
                    <a href={a.meeting} target="_blank" rel="noreferrer" className="zr-source">
                      Council agenda ↗
                    </a>
                  )}
                </div>
                <p className="zr-tag">{a.reasons.join("; ")}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="zr-muted">
            No stored amendment to By-law 8149/24 names this lot&apos;s address, lot and concession, or exception zone.
          </p>
        )}
        <h4>Official Plan designation</h4>
        <p>{frameworks.official_plan_designation.filter(Boolean).join(", ") || "Not in the City layers"}</p>
        <h4>Provincial</h4>
        <ul className="zr-plain">
          {frameworks.provincial.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <h4>Every stored by-law, plan and regulation</h4>
        {Object.entries(frameworks.all_documents).map(([group, list]) => (
          <details key={group} className="zr-overlay">
            <summary>
              {GROUP_LABELS[group] ?? group} <span>{list.length}</span>
            </summary>
            <ul className="zr-plain">
              {list.map((doc) => (
                <li key={doc.file}>
                  <a href={docUrl(doc.file)} target="_blank" rel="noreferrer">
                    {doc.title}
                  </a>
                  {doc.pages ? <span className="zr-muted"> · {doc.pages} pages</span> : null}
                </li>
              ))}
            </ul>
          </details>
        ))}
      </Step>
    </div>
  );
}
