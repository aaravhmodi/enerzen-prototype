"use client";

import { useEffect, useId, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  lookupPoint,
  lotForForm,
  mapAround,
  searchAddresses,
  type Candidate,
  type Lookup,
  type LotForForm,
  type MapData,
} from "@/lib/zoning";
import { useUnits } from "@/lib/units";
import "@/app/zoning/zoning.css";

// mapbox-gl touches window on import, so it loads in the browser only.
const ZoningMap = dynamic(() => import("@/components/ZoningMap"), {
  ssr: false,
  loading: () => <div className="zoning-map zoning-map--empty">Loading map…</div>,
});

// Map layers drawn around the chosen lot; the rest of the City's layers stay on the zoning page.
const HIDDEN = new Set(["other", "neighbourhoods", "addresses"]);

// Choose a Pickering lot by address or on the map, and hand its size, street side and by-law
// setbacks to the form, so they are read from the City's data rather than typed in.
export default function LotPicker({ onLot }: { onLot: (lot: LotForForm) => void }) {
  const u = useUnits();
  const inputId = useId();
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [mapData, setMapData] = useState<MapData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2 || text === chosen) return;
    const timer = window.setTimeout(async () => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      try {
        setCandidates(await searchAddresses(text, controller.signal));
      } catch {
        // A search typed over by the next keystroke is aborted; nothing to show.
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, chosen]);

  const choose = async (label: string, latitude: number, longitude: number) => {
    setQuery(label);
    setChosen(label);
    setCandidates([]);
    setLoading(true);
    setError(null);
    try {
      const [found, around] = await Promise.all([lookupPoint(latitude, longitude), mapAround(latitude, longitude)]);
      setLookup(found);
      setMapData(around);
      const lot = lotForForm(found);
      if (lot) onLot(lot);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The lot could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  const standards = lookup?.steps?.["3_proposed_development"].lot_standards;
  const lot = lookup ? lotForForm(lookup) : null;
  const read = lot
    ? ([["front", lot.front_setback_m], ["side", lot.side_setback_m], ["rear", lot.rear_setback_m]] as const)
    : [];
  const address = lookup?.steps?.["1_property_identification"].from_city_data?.address;

  return (
    <div className="lot-picker">
      <div className="zoning-search section-card">
        <label htmlFor={inputId} className="tile-label">
          Find your lot in Pickering
        </label>
        <input
          id={inputId}
          className="input"
          placeholder="Address, roll number or PIN, or click the map"
          value={query}
          autoComplete="off"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && candidates[0]) {
              e.preventDefault();
              const c = candidates[0];
              void choose(c.label, c.latitude, c.longitude);
            }
          }}
        />
        {candidates.length > 0 && query !== chosen && (
          <ul className="zoning-candidates" role="listbox">
            {candidates.map((c) => (
              <li key={`${c.source}-${c.label}-${c.latitude}`}>
                <button type="button" onClick={() => void choose(c.label, c.latitude, c.longitude)}>
                  <span>{c.label}</span>
                  <small>{c.detail}</small>
                </button>
              </li>
            ))}
          </ul>
        )}
        {loading && <p className="zr-muted">Reading the City&apos;s data and the by-law for this lot…</p>}
        {error && <p className="zr-warning">{error}</p>}
        {!loading && lookup && lot && (
          <div className="zr-muted" aria-live="polite">
            <p>
              {address || chosen}
              {standards?.zone_code ? ` · Zone ${standards.zone_code}` : ""}
              {lot.lot_width_m ? ` · ${u.dims(lot.lot_width_m, lot.lot_depth_m ?? 0)}` : ""}
              {lot.street_side ? ` · street to the ${lot.street_side}` : ""}
            </p>
            <p>
              {read.some(([, v]) => v != null)
                ? `From the by-law: ${read
                    .filter(([, v]) => v != null)
                    .map(([name, v]) => `${name} ${u.length(v!)}`)
                    .join(", ")}.`
                : "The by-law gave no setbacks this form can use for this lot."}
              {read.some(([, v]) => v == null) &&
                ` Not found, so still your own: ${read
                  .filter(([, v]) => v == null)
                  .map(([name]) => name)
                  .join(", ")}.`}{" "}
              {standards?.basis_note && standards.basis !== "yards" ? standards.basis_note : ""}
            </p>
            <Link
              href={`/zoning?lat=${lot.latitude.toFixed(6)}&lng=${lot.longitude.toFixed(6)}&q=${encodeURIComponent(chosen ?? "")}`}
              target="_blank"
            >
              Full zoning review for this lot
            </Link>
          </div>
        )}
      </div>
      <ZoningMap
        data={mapData}
        envelope={lookup?.buildable_area ?? null}
        hidden={HIDDEN}
        onPick={(lat, lng) => void choose(`${lat.toFixed(5)}, ${lng.toFixed(5)}`, lat, lng)}
      />
    </div>
  );
}
