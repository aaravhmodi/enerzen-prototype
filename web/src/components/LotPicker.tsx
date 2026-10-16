"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  CATEGORY_LABELS,
  docUrl,
  lookupPoint,
  lotForForm,
  mapAround,
  searchBylaws,
  searchAddresses,
  type Candidate,
  type Lookup,
  type LotForForm,
  type MapData,
  type SearchResult,
} from "@/lib/zoning";
import { useUnits } from "@/lib/units";
import type { SiteSpecInput } from "@/lib/api";
import ZoningReview from "@/components/ZoningReview";
import "@/app/zoning/zoning.css";

// mapbox-gl touches window on import, so it loads in the browser only.
const ZoningMap = dynamic(() => import("@/components/ZoningMap"), {
  ssr: false,
  loading: () => <div className="zoning-map zoning-map--empty">Loading map…</div>,
});

const DEFAULT_HIDDEN = ["other", "neighbourhoods", "addresses"];

// Choose a Pickering lot by address or on the map, and hand its size, street side and by-law
// setbacks to the form, so they are read from the City's data rather than typed in.
export default function LotPicker({
  onLot,
  initialSite,
}: {
  onLot: (lot: LotForForm) => void;
  initialSite?: Partial<SiteSpecInput> | null;
}) {
  const u = useUnits();
  const inputId = useId();
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [mapData, setMapData] = useState<MapData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hidden, setHidden] = useState(() => new Set(DEFAULT_HIDDEN));
  const [bylawQuery, setBylawQuery] = useState("");
  const [bylawResults, setBylawResults] = useState<{ total: number; results: SearchResult[] } | null>(null);
  const [bylawLoading, setBylawLoading] = useState(false);
  const [bylawError, setBylawError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const didInitialLookup = useRef(false);

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

  const choose = useCallback(async (label: string, latitude: number, longitude: number) => {
    setQuery(label);
    setChosen(label);
    setCandidates([]);
    setLoading(true);
    setError(null);
    try {
      const [found, around] = await Promise.all([lookupPoint(latitude, longitude), mapAround(latitude, longitude, 400)]);
      setLookup(found);
      setMapData(around);
      const lot = lotForForm(found);
      if (lot) onLot(lot);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The lot could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [onLot]);

  useEffect(() => {
    const latitude = initialSite?.latitude;
    const longitude = initialSite?.longitude;
    if (didInitialLookup.current || latitude == null || longitude == null) return;
    didInitialLookup.current = true;
    void choose(`${latitude.toFixed(5)}, ${longitude.toFixed(5)}`, latitude, longitude);
  }, [initialSite?.latitude, initialSite?.longitude, choose]);

  const toggleLayer = (category: string) =>
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });

  const searchDocuments = async () => {
    if (!bylawQuery.trim()) return;
    setBylawLoading(true);
    setBylawError(null);
    try {
      setBylawResults(await searchBylaws(bylawQuery.trim()));
    } catch (e) {
      setBylawError(e instanceof Error ? e.message : "Search failed.");
    } finally {
      setBylawLoading(false);
    }
  };

  const standards = lookup?.steps?.["3_proposed_development"].lot_standards;
  const lot = lookup ? lotForForm(lookup) : null;
  const read = lot
    ? ([["front", lot.front_setback_m], ["side", lot.side_setback_m], ["rear", lot.rear_setback_m]] as const)
    : [];
  const address = lookup?.steps?.["1_property_identification"].from_city_data?.address;
  const categories = [...new Set(mapData?.layers.map((layer) => layer.category) ?? [])];

  return (
    <div className="lot-picker">
      <div className="zoning-search section-card">
        <p className="lot-picker-intro">
          Choose the parcel for this project. Its zoning, overlays, and by-law standards stay with your site brief as you continue.
        </p>
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
          </div>
        )}
      </div>
      <ZoningMap
        data={mapData}
        envelope={lookup?.buildable_area ?? null}
        hidden={hidden}
        onPick={(lat, lng) => void choose(`${lat.toFixed(5)}, ${lng.toFixed(5)}`, lat, lng)}
        onExplore={async (lat, lng) => {
          try {
            const around = await mapAround(lat, lng, 400);
            setMapData((current) => ({ ...around, parcel: current?.parcel ?? null, explored: true }));
          } catch {
            // Keep the loaded layers visible if a pan cannot load another area.
          }
        }}
      />
      {categories.length > 0 && (
        <div className="zoning-legend section-card" aria-label="Map layers">
          {categories.map((category) => {
            const color = mapData?.layers.find((layer) => layer.category === category)?.color ?? "#64748b";
            const count = mapData?.layers
              .filter((layer) => layer.category === category)
              .reduce((total, layer) => total + layer.features.features.length, 0);
            return (
              <label key={category}>
                <input type="checkbox" checked={!hidden.has(category)} onChange={() => toggleLayer(category)} />
                <i style={{ background: color }} aria-hidden="true" />
                {CATEGORY_LABELS[category] ?? category}
                <small>{count}</small>
              </label>
            );
          })}
        </div>
      )}
      {lookup && (
        <details className="lot-picker-details section-card">
          <summary>Review zoning, overlays, and planning requirements</summary>
          <ZoningReview lookup={lookup} embedded />
        </details>
      )}
      <details className="lot-picker-details section-card">
        <summary>Search Pickering by-laws and planning documents</summary>
        <div className="zoning-bylaw-form">
          <label htmlFor={`${inputId}-bylaw`} className="tile-label">
            Search stored by-laws, plans, and regulations
          </label>
          <div>
            <input
              id={`${inputId}-bylaw`}
              className="input"
              placeholder="e.g. R4, minimum lot frontage, garden suite, parking"
              value={bylawQuery}
              onChange={(event) => setBylawQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void searchDocuments();
                }
              }}
            />
            <button type="button" className="quiet-button" onClick={() => void searchDocuments()} disabled={bylawLoading || !bylawQuery.trim()}>
              {bylawLoading ? "Searching…" : "Search"}
            </button>
          </div>
        </div>
        {bylawError && <p className="zr-warning">{bylawError}</p>}
        {bylawResults && (
          <>
            <p className="zr-muted">
              {bylawResults.total} page{bylawResults.total === 1 ? "" : "s"} mention “{bylawQuery}”
              {bylawResults.total > bylawResults.results.length ? `, first ${bylawResults.results.length}` : ""}
            </p>
            <ul className="zr-refs">
              {bylawResults.results.map((result) => (
                <li key={`${result.file}-${result.page}`}>
                  <div className="zr-hit-head">
                    <a href={docUrl(result.file, result.page)} target="_blank" rel="noreferrer">
                      {result.title}, p. {result.page}
                    </a>
                    <span>{result.hits_on_page} matches</span>
                  </div>
                  <blockquote>{result.snippet}</blockquote>
                </li>
              ))}
            </ul>
          </>
        )}
      </details>
    </div>
  );
}
