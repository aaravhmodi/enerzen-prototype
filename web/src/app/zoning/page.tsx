"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import ZoningReview from "@/components/ZoningReview";
import {
  CATEGORY_LABELS,
  dataStatus,
  docUrl,
  lookupPoint,
  mapAround,
  searchAddresses,
  searchBylaws,
  setbackCoverage,
  SETBACKS_CSV,
  type SetbackCoverage,
  type Candidate,
  type Lookup,
  type MapData,
  type SearchResult,
} from "@/lib/zoning";

// mapbox-gl touches window on import, so it loads in the browser only.
const ZoningMap = dynamic(() => import("@/components/ZoningMap"), {
  ssr: false,
  loading: () => <div className="zoning-map zoning-map--empty">Loading map…</div>,
});

type Tab = "review" | "bylaws";
type Report = NonNullable<Awaited<ReturnType<typeof dataStatus>>["completeness"]>;

// What the last scrape could not get, so a gap is never mistaken for "no rule".
function Completeness({ report }: { report: Report }) {
  if (report.complete) return <p className="zr-ok">Complete: every published layer and cited by-law is stored.</p>;
  const gaps = [
    report.incomplete_layers.length && `${report.incomplete_layers.length} layers short of the server's count`,
    report.not_downloaded.length && `${report.not_downloaded.length} layers not downloaded`,
    report.missing_bylaws.length && `cited by-laws not found: ${report.missing_bylaws.join(", ")}`,
    report.pdfs_with_blank_pages && `${report.pdfs_with_blank_pages} PDFs with unreadable pages`,
    report.documents_carried_over &&
      `${report.documents_carried_over} documents kept from the last run (the City could not serve them)`,
    report.errors && `${report.errors} download errors`,
  ].filter(Boolean);
  return (
    <details className="zr-gaps">
      <summary>Data gaps: {gaps.length}</summary>
      <ul className="zr-plain">
        {gaps.map((gap) => (
          <li key={String(gap)}>{gap}</li>
        ))}
      </ul>
    </details>
  );
}

export default function ZoningPage() {
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<{ label: string; latitude: number; longitude: number } | null>(null);
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [mapData, setMapData] = useState<MapData | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set(["other", "neighbourhoods", "addresses"]));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("review");
  const [status, setStatus] = useState<Awaited<ReturnType<typeof dataStatus>> | null>(null);
  const [bylawQuery, setBylawQuery] = useState("");
  const [bylawResults, setBylawResults] = useState<{ total: number; results: SearchResult[] } | null>(null);
  const abort = useRef<AbortController | null>(null);

  const [coverage, setCoverage] = useState<SetbackCoverage | null>(null);
  useEffect(() => {
    dataStatus().then(setStatus).catch(() => setStatus(null));
    setbackCoverage().then(setCoverage).catch(() => setCoverage(null));
  }, []);

  const review = useCallback(async (label: string, latitude: number, longitude: number) => {
    setSelected({ label, latitude, longitude });
    setCandidates([]);
    setLoading(true);
    setError(null);
    setTab("review");
    try {
      const [lot, around] = await Promise.all([lookupPoint(latitude, longitude), mapAround(latitude, longitude)]);
      setLookup(lot);
      setMapData(around);
      const url = new URL(window.location.href);
      url.searchParams.set("lat", latitude.toFixed(6));
      url.searchParams.set("lng", longitude.toFixed(6));
      url.searchParams.set("q", label);
      window.history.replaceState(null, "", url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The lot could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  // A shared link (?lat=&lng=&q=) opens straight onto its lot.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const lat = Number(params.get("lat"));
    const lng = Number(params.get("lng"));
    if (!params.get("lat") || !Number.isFinite(lat) || !Number.isFinite(lng)) return;
    const label = params.get("q") ?? `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
    const timer = window.setTimeout(() => {
      setQuery(label);
      void review(label, lat, lng);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [review]);

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2 || text === selected?.label) return;
    const timer = window.setTimeout(async () => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      setSearching(true);
      try {
        setCandidates(await searchAddresses(text, controller.signal));
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, selected?.label]);

  const toggle = (category: string) =>
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });

  const runBylawSearch = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!bylawQuery.trim()) return;
    try {
      setBylawResults(await searchBylaws(bylawQuery));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed.");
    }
  };

  // Suggestions only while the box holds something new to look up.
  const suggesting = query.trim().length >= 2 && query.trim() !== selected?.label;
  const shown = suggesting ? candidates : [];
  const categories = [...new Set(mapData?.layers.map((l) => l.category) ?? [])];
  const notScraped = status?.status === "not_scraped";

  return (
    <div className="enerzen-app zoning-page">
      <div className="ambient" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
      <header className="app-header">
        <Link className="wordmark" href="/" aria-label="EnerZen home">
          <span className="brand-symbol" aria-hidden="true">
            e
          </span>
          enerzen
          <span className="brand-dot" aria-hidden="true">
            •
          </span>
        </Link>
        <nav aria-label="Main navigation">
          <span className="pilot-chip">
            <span /> Pickering zoning
          </span>
          <Link className="quiet-button" href="/">
            Workspace <span aria-hidden="true">↗</span>
          </Link>
        </nav>
      </header>

      <main id="main-content" className="zoning-layout animate-screen-in">
        <section className="zoning-left">
          <div className="zoning-search panel">
            <p className="eyebrow">Find a lot in Pickering</p>
            <label htmlFor="zoning-address" className="sr-only">
              Address, roll number or PIN
            </label>
            <input
              id="zoning-address"
              className="input"
              placeholder="Address, roll number or PIN"
              value={query}
              autoComplete="off"
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && shown[0]) {
                  const c = shown[0];
                  setQuery(c.label);
                  void review(c.label, c.latitude, c.longitude);
                }
              }}
            />
            {suggesting && (shown.length > 0 || searching) && (
              <ul className="zoning-candidates" role="listbox">
                {searching && !shown.length && <li className="zr-muted">Searching…</li>}
                {shown.map((c) => (
                  <li key={`${c.source}-${c.label}-${c.latitude}`}>
                    <button
                      type="button"
                      onClick={() => {
                        setQuery(c.label);
                        void review(c.label, c.latitude, c.longitude);
                      }}
                    >
                      <span>{c.label}</span>
                      <small>{c.detail}</small>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {notScraped && (
              <p className="zr-warning">
                The server has no Pickering data yet. Run <code>docker compose run --rm scrape-pickering</code> on it.
              </p>
            )}
            {status?.status === "available" && (
              <>
                <p className="zr-muted">
                  City data from {status.retrieved_at?.slice(0, 10)} ·{" "}
                  {Object.values(status.layers ?? {}).flat().length} layers · {status.documents} documents ·{" "}
                  {status.council_amendments ?? 0} council amendments
                </p>
                {status.completeness && <Completeness report={status.completeness} />}
                {coverage && coverage.lots > 0 && (
                  <p className="zr-muted">
                    Setbacks from the by-law for {coverage.complete.toLocaleString()} of{" "}
                    {coverage.lots.toLocaleString()} lots ·{" "}
                    <a href={SETBACKS_CSV} download>
                      Every lot as CSV
                    </a>
                  </p>
                )}
              </>
            )}
          </div>

          <ZoningMap
            data={mapData}
            envelope={lookup?.buildable_area ?? null}
            hidden={hidden}
            onExplore={async (lat, lng) => {
              try {
                const around = await mapAround(lat, lng, 400);
                // Keep the chosen lot outlined while showing the layers around the new view.
                setMapData((current) => ({ ...around, parcel: current?.parcel ?? null, explored: true }));
              } catch {
                // Panning is a convenience; the chosen lot's layers stay on screen.
              }
            }}
            onPick={(lat, lng) => {
              const label = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
              setQuery(label);
              void review(label, lat, lng);
            }}
          />

          {categories.length > 0 && (
            <div className="zoning-legend panel" aria-label="Map layers">
              {categories.map((category) => {
                const color = mapData?.layers.find((l) => l.category === category)?.color ?? "#64748b";
                const count = mapData?.layers
                  .filter((l) => l.category === category)
                  .reduce((n, l) => n + l.features.features.length, 0);
                return (
                  <label key={category}>
                    <input type="checkbox" checked={!hidden.has(category)} onChange={() => toggle(category)} />
                    <i style={{ background: color }} aria-hidden="true" />
                    {CATEGORY_LABELS[category] ?? category}
                    <small>{count}</small>
                  </label>
                );
              })}
            </div>
          )}
        </section>

        <section className="zoning-right" aria-live="polite">
          <div className="zoning-tabs" role="tablist">
            <button role="tab" aria-selected={tab === "review"} onClick={() => setTab("review")}>
              Lot review
            </button>
            <button role="tab" aria-selected={tab === "bylaws"} onClick={() => setTab("bylaws")}>
              Search all by-laws
            </button>
          </div>

          {error && <p className="zr-warning">{error}</p>}

          {tab === "review" && (
            <>
              {selected && <h1 className="zoning-title">{selected.label}</h1>}
              {loading && <p className="zr-muted">Reading the City&apos;s layers and by-laws for this lot…</p>}
              {!loading && lookup && <ZoningReview lookup={lookup} />}
              {!selected && !loading && (
                <div className="section-card">
                  <p className="eyebrow">How it works</p>
                  <p>
                    Search an address, roll number or PIN, or click anywhere on the map. The lot is drawn from the
                    City of Pickering&apos;s parcel data stored on this server, with its zoning, Official Plan
                    designation, overlays and the by-law pages that govern it.
                  </p>
                </div>
              )}
            </>
          )}

          {tab === "bylaws" && (
            <div className="section-card">
              <form onSubmit={runBylawSearch} className="zoning-bylaw-form">
                <label htmlFor="bylaw-q" className="tile-label">
                  Search every stored by-law, plan and regulation
                </label>
                <div>
                  <input
                    id="bylaw-q"
                    className="input"
                    placeholder="e.g. R4, minimum lot frontage, garden suite, parking"
                    value={bylawQuery}
                    onChange={(e) => setBylawQuery(e.target.value)}
                  />
                  <button type="submit" className="quiet-button">
                    Search
                  </button>
                </div>
              </form>
              {bylawResults && (
                <>
                  <p className="zr-muted">
                    {bylawResults.total} page{bylawResults.total === 1 ? "" : "s"} mention “{bylawQuery}”
                    {bylawResults.total > bylawResults.results.length ? `, first ${bylawResults.results.length}` : ""}
                  </p>
                  <ul className="zr-refs">
                    {bylawResults.results.map((r) => (
                      <li key={`${r.file}-${r.page}`}>
                        <div className="zr-hit-head">
                          <a href={docUrl(r.file, r.page)} target="_blank" rel="noreferrer">
                            {r.title}, p. {r.page}
                          </a>
                          <span>{r.hits_on_page}×</span>
                        </div>
                        <blockquote>{r.snippet}</blockquote>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
