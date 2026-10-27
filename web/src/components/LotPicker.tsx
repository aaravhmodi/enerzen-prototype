"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  CATEGORY_LABELS,
  docUrl,
  lookupPoint,
  lotForForm,
  mapAround,
  addressesAtPoint,
  pilotArea,
  pilotRefusal,
  searchBylaws,
  searchAddresses,
  type Candidate,
  type Lookup,
  type LotForForm,
  type MapData,
  type PilotArea,
  type SearchResult,
} from "@/lib/zoning";
import { useUnits } from "@/lib/units";
import type { SiteSpecInput } from "@/lib/api";
import type { Geometry } from "geojson";
import ZoningReview from "@/components/ZoningReview";
import "@/app/zoning/zoning.css";

// mapbox-gl touches window on import, so it loads in the browser only.
const ZoningMap = dynamic(() => import("@/components/ZoningMap"), {
  ssr: false,
  loading: () => <div className="zoning-map zoning-map--empty">Loading map…</div>,
});

// Start with the zoning overlay only. Extra city layers are available on demand;
// stacking every polygon layer at once makes lot boundaries hard to read.
const DEFAULT_HIDDEN = [
  "parcels", "official_plan", "floodplain", "natural_heritage", "heritage",
  "easements", "rail", "provincial_plans", "servicing", "topography",
  "addresses", "neighbourhoods", "roads", "other",
];

// Choose a Pickering lot by address or on the map, and hand its size, street side and by-law
// setbacks to the form, so they are read from the City's data rather than typed in.
export default function LotPicker({
  onLot,
  initialSite,
  lotWidth,
  lotDepth,
  onLotResize,
  resume,
}: {
  onLot: (lot: LotForForm) => void;
  initialSite?: Partial<SiteSpecInput> | null;
  // A lot picked on an earlier visit to this step: shown again without overwriting the form.
  resume?: { latitude?: number | null; longitude?: number | null } | null;
  lotWidth?: number;
  lotDepth?: number;
  onLotResize?: (width: number, depth: number) => void;
}) {
  const u = useUnits();
  const inputId = useId();
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [workingPoint, setWorkingPoint] = useState<{ latitude: number; longitude: number } | null>(null);
  const [workingBoundary, setWorkingBoundary] = useState<Geometry | null>(null);
  const [mapData, setMapData] = useState<MapData | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchingAddresses, setSearchingAddresses] = useState(false);
  const [pointSearch, setPointSearch] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hidden, setHidden] = useState(() => new Set(DEFAULT_HIDDEN));
  const [bylawQuery, setBylawQuery] = useState("");
  const [bylawResults, setBylawResults] = useState<{ total: number; results: SearchResult[] } | null>(null);
  const [bylawLoading, setBylawLoading] = useState(false);
  const [bylawError, setBylawError] = useState<string | null>(null);
  const [pilot, setPilot] = useState<PilotArea | null>(null);
  const abort = useRef<AbortController | null>(null);
  const didInitialLookup = useRef(false);
  const [resumeAt] = useState(resume);

  useEffect(() => {
    pilotArea().then(setPilot).catch(() => setPilot(null));
  }, []);

  useEffect(() => {
    const text = query.trim();
    if (pointSearch || text.length < 2 || text === chosen) return;
    const timer = window.setTimeout(async () => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      setSearchingAddresses(true);
      try {
        setCandidates(await searchAddresses(text, controller.signal));
      } catch {
        // A search typed over by the next keystroke is aborted; nothing to show.
      } finally {
        if (!controller.signal.aborted) setSearchingAddresses(false);
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, chosen, pointSearch]);

  const findAddressesAtPoint = useCallback(async (latitude: number, longitude: number) => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setPointSearch(true);
    setChosen(null);
    setQuery(`Near ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`);
    setCandidates([]);
    setSearchingAddresses(true);
    setError(null);
    try {
      const nearby = await addressesAtPoint(latitude, longitude, controller.signal);
      setCandidates(nearby.length ? nearby : [{
        label: `Use map pin · ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`,
        latitude, longitude, source: "mapbox", detail: "No nearby street address found",
      }]);
    } catch (e) {
      if (!controller.signal.aborted) {
        setCandidates([{
          label: `Use map pin · ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`,
          latitude, longitude, source: "mapbox", detail: "Address lookup unavailable",
        }]);
        setError(e instanceof Error ? e.message : "Nearby addresses could not be found.");
      }
    } finally {
      if (!controller.signal.aborted) setSearchingAddresses(false);
    }
  }, []);

  const choose = useCallback(async (label: string, latitude: number, longitude: number, apply = true) => {
    abort.current?.abort();
    setPointSearch(false);
    setQuery(label);
    setChosen(label);
    setCandidates([]);
    setLoading(true);
    setError(null);
    try {
      const [found, around] = await Promise.all([lookupPoint(latitude, longitude), mapAround(latitude, longitude, 400)]);
      setLookup(found);
      setMapData(around);
      const refusal = pilotRefusal(found);
      if (refusal) {
        // Shown on the map for context, but never handed to the brief.
        setWorkingPoint(null);
        setWorkingBoundary(null);
        setError(refusal);
        return;
      }
      // The City's parcel fabric stores every lot as a one-part MultiPolygon.
      const outline = around.parcel?.geometry;
      setWorkingBoundary(
        outline?.type === "Polygon" ? outline
          : outline?.type === "MultiPolygon" && outline.coordinates.length === 1 ? { type: "Polygon", coordinates: outline.coordinates[0] }
          : null,
      );
      const lot = lotForForm(found);
      if (lot) {
        setWorkingPoint({ latitude: lot.latitude, longitude: lot.longitude });
        if (apply) onLot(lot);
        else {
          const shown = found.steps?.["1_property_identification"].from_city_data?.address ?? label;
          setQuery(shown);
          setChosen(shown);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "The lot could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [onLot]);

  useEffect(() => {
    const apply = resumeAt?.latitude == null || resumeAt?.longitude == null;
    const latitude = apply ? initialSite?.latitude : resumeAt?.latitude;
    const longitude = apply ? initialSite?.longitude : resumeAt?.longitude;
    if (didInitialLookup.current || latitude == null || longitude == null) return;
    didInitialLookup.current = true;
    void choose(`${latitude.toFixed(5)}, ${longitude.toFixed(5)}`, latitude, longitude, apply);
  }, [initialSite?.latitude, initialSite?.longitude, resumeAt, choose]);

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
  const lot = lookup && !pilotRefusal(lookup) ? lotForForm(lookup) : null;
  const read = lot
    ? ([["front", lot.front_setback_m], ["side", lot.side_setback_m], ["rear", lot.rear_setback_m]] as const)
    : [];
  const address = lookup?.steps?.["1_property_identification"].from_city_data?.address;
  const sideYards = Object.values(standards?.setbacks_by_side ?? {})
    .filter((v) => v.applies === "interior_side_yard" && v.value != null)
    .map((v) => v.value!);
  const categories = [...new Set(mapData?.layers.map((layer) => layer.category) ?? [])];
  const workingLot = useMemo(
    () => workingPoint && lotWidth != null && lotDepth != null
      ? { ...workingPoint, width_m: lotWidth, depth_m: lotDepth }
      : null,
    [workingPoint, lotWidth, lotDepth],
  );
  const editableLot = useMemo(
    () => workingLot ? { ...workingLot, boundary: workingBoundary } : null,
    [workingLot, workingBoundary],
  );

  return (
    <div className="lot-picker">
      <div className="zoning-search section-card">
        <p className="lot-picker-intro">
          Choose the parcel for this project. Its zoning, overlays, and by-law standards stay with your site brief as you continue.
        </p>
        {pilot?.boundary && (
          <p className="zr-muted">
            EnerZen covers the <strong>{pilot.name}</strong> neighbourhood for now, outlined in green on the map. The
            outline is the City of Pickering&apos;s official neighbourhood boundary
            {pilot.profile && (
              <>
                {" "}(<a href={pilot.profile} target="_blank" rel="noreferrer">City profile</a>)
              </>
            )}
            ; street names on the base map are only for finding your way. Every zoning rule inside it is read straight
            from the current by-law text.
            {pilot.unverified?.features.length
              ? ` ${pilot.unverified.features.length} of its ${pilot.lots} lots are greyed out because one of their rules could not be read that way.`
              : ""}
          </p>
        )}
        <label htmlFor={inputId} className="tile-label">
          Find your lot in {pilot?.boundary ? pilot.name : "Pickering"}
        </label>
        <input
          id={inputId}
          className="input"
          placeholder="Address, roll number or PIN, or click the map"
          value={query}
          autoComplete="off"
          onChange={(e) => { setPointSearch(false); setCandidates([]); setQuery(e.target.value); }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && candidates[0]) {
              e.preventDefault();
              const c = candidates[0];
              void choose(c.label, c.latitude, c.longitude);
            }
          }}
        />
        {!query && !lookup && !loading && (
          <p className="zr-muted">
            {/* A lot whose every rule the by-law text supplies, so a first look never lands on a greyed-out one. */}
            Not sure where to start?{" "}
            <button type="button" className="zr-more" onClick={() => void choose("650 CHIRON CRES", 43.8305, -79.1252)}>
              Try an example lot: 650 Chiron Cres
            </button>
          </p>
        )}
        {searchingAddresses && (
          <p className="lot-picker-thinking" role="status">
            <span className="lot-picker-spinner" aria-hidden="true" />
            {pointSearch ? "Finding addresses near the pin" : "Searching addresses"}
          </p>
        )}
        {pointSearch && candidates.length > 0 && !searchingAddresses && (
          <p className="zr-muted">Choose the address that matches this map location.</p>
        )}
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
        {loading && (
          <p className="lot-picker-thinking" role="status">
            <span className="lot-picker-spinner" aria-hidden="true" />
            Reading the City&apos;s data and the by-law for this address
          </p>
        )}
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
              {sideYards.length === 2 && sideYards[0] !== sideYards[1]
                ? `The by-law sets side yards of ${sideYards.map(u.length).join(" and ")}; the site plan applies the larger to both sides. `
                : ""}
              {standards?.basis_note && standards.basis !== "yards" ? standards.basis_note : ""}
            </p>
          </div>
        )}
      </div>
      <ZoningMap
        data={mapData}
        hidden={hidden}
        onPick={(lat, lng) => void findAddressesAtPoint(lat, lng)}
        onExplore={async (lat, lng) => {
          try {
            const around = await mapAround(lat, lng, 400);
            setMapData((current) => ({ ...around, parcel: current?.parcel ?? null, explored: true }));
          } catch {
            // Keep the loaded layers visible if a pan cannot load another area.
          }
        }}
        workingLot={editableLot}
        pilot={pilot}
        onLotResize={(width, depth, boundary) => {
          setWorkingBoundary(boundary);
          onLotResize?.(width, depth);
        }}
      />
      {workingPoint && (
        <p className="lot-map-instructions" aria-live="polite">
          {workingBoundary
            ? "Selected parcel shown in gold. Drag a corner handle to adjust the boundary; the lot dimensions below update with the map."
            : "No parcel outline is available for this address yet. The gold rectangle is an editable estimate; drag a corner handle to shape it."}
        </p>
      )}
      {categories.length > 0 && (
        <details className="zoning-legend-panel section-card">
          <summary>Map layers ({categories.length})</summary>
          <div className="zoning-legend" aria-label="Map layers">
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
        </details>
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
