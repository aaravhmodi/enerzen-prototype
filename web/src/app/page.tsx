"use client";

import { useState, useEffect, useRef, type CSSProperties } from "react";
import ProjectForm, { FormState, PROJECT_FIELD_STEP } from "@/components/ProjectForm";
import ResultsPanel from "@/components/ResultsPanel";
import SitePlanView from "@/components/SitePlanView";
import DevForm, { DEV_FIELD_STEP } from "@/components/DevForm";
import DevResults from "@/components/DevResults";
import MultiSitePlanView from "@/components/MultiSitePlanView";
import DevScenarioReview from "@/components/DevScenarioReview";
import DevRecommendation from "@/components/DevRecommendation";
import Architecture from "@/components/Architecture";
import { fmtCad, setUnitSystem, useUnits, type UnitSystem } from "@/lib/units";
import ExploringStage, { type ExploringContext } from "@/components/ExploringStage";
import { errorInfo, type FieldError, type SiteSpecInput } from "@/lib/api";
import {
  ConfigResult,
  ExcludedType,
  GateBreakdown,
  SoftSummary,
  SiteLayout,
  runOptimize,
  runReport,
  runSitePlan,
  DevSpecInput,
  DevMixResult,
  DevScenario,
  RejectedMix,
  runDevOptimize,
  runDevReport,
  runDevScenarios,
  runDevSitePlan,
} from "@/lib/api";

type Screen = "welcome" | "path" | "single" | "development";

// Long enough to read the first few narrated stages when the engine is fast.
const MIN_EXPLORE_MS = 2600;
const pause = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));
// Delay for one step of the staged results reveal.
const at = (seconds: number) => ({ "--d": `${seconds}s` }) as CSSProperties;

// The zoning map hands a real Pickering lot to the workspace as /?lot=lat,lng&w=&d=&street=.
function lotFromUrl(): Partial<SiteSpecInput> | null {
  const params = new URLSearchParams(window.location.search);
  const [lat, lng] = (params.get("lot") ?? "").split(",").map(Number);
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || !params.get("lot")) return null;
  const site: Partial<SiteSpecInput> = { latitude: lat, longitude: lng };
  const width = Number(params.get("w"));
  const depth = Number(params.get("d"));
  if (width > 0) site.lot_width_m = width;
  if (depth > 0) site.lot_depth_m = depth;
  for (const [param, key] of [["front", "front_setback_m"], ["side", "side_setback_m"], ["rear", "rear_setback_m"]] as const) {
    const value = Number(params.get(param));
    if (params.get(param) && Number.isFinite(value) && value >= 0) site[key] = value;
  }
  const street = params.get("street");
  if (street === "N" || street === "S" || street === "E" || street === "W") site.street_side = street;
  return site;
}

export default function Home() {
  const [screen, setScreen] = useState<Screen>("welcome");
  const u = useUnits();
  const [lot, setLot] = useState<Partial<SiteSpecInput> | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const fromMap = lotFromUrl();
      if (!fromMap) return;
      setLot(fromMap);
      setScreen("single");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const [viewResults, setViewResults] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    window.scrollTo({ top: 0 });
    heading.current?.focus();
  }, [screen, viewResults]);

  // ── Single-unit state ──────────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<FieldError | null>(null);
  const [results, setResults] = useState<ConfigResult[] | null>(null);
  const [soft, setSoft] = useState<SoftSummary | null>(null);
  const [gate, setGate] = useState<GateBreakdown | null>(null);
  const [siteData, setSiteData] = useState<{
    layout: SiteLayout;
    svg: string;
    concept: string | null;
  } | null>(null);
  const [lastState, setLastState] = useState<FormState | null>(null);
  const [downloadingReport, setDownloadingReport] = useState(false);

  // ── Development-plan state ─────────────────────────────────────────────────
  const [devSubmitting, setDevSubmitting] = useState(false);
  const [devError, setDevError] = useState<FieldError | null>(null);
  const [devMixes, setDevMixes] = useState<DevMixResult[] | null>(null);
  const [devSvg, setDevSvg] = useState<string | null>(null);
  const [devConcept, setDevConcept] = useState<string | null>(null);
  const [selectedMix, setSelectedMix] = useState(0);
  const [lastDevSpec, setLastDevSpec] = useState<DevSpecInput | null>(null);
  const [devIterations, setDevIterations] = useState(0);
  // Flowchart Path B: brief -> site plan review (max 3) -> performance optimization -> ranking.
  const [devStage, setDevStage] = useState<"brief" | "review" | "final">("brief");
  const [devPhase, setDevPhase] = useState<"scenarios" | "performance">("scenarios");
  const [scenarios, setScenarios] = useState<DevScenario[] | null>(null);
  const [approved, setApproved] = useState<boolean[]>([]);
  const [selectedScenario, setSelectedScenario] = useState(0);
  const [rejectedMixes, setRejectedMixes] = useState<RejectedMix[]>([]);
  const [excludedTypes, setExcludedTypes] = useState<ExcludedType[]>([]);
  const [zoningNotes, setZoningNotes] = useState<string[]>([]);
  const [approvedMixes, setApprovedMixes] = useState<Record<string, number>[]>([]);
  const [downloadingDevReport, setDownloadingDevReport] = useState(false);
  const [softFraction, setSoftFraction] = useState(0.25);

  // ── Handlers ───────────────────────────────────────────────────────────────
  async function handleSingleSubmit(state: FormState) {
    setSubmitting(true);
    setError(null);
    setLastState(state);
    try {
      const [optimizeRes, siteRes] = await Promise.all([
        runOptimize(
          state.spec,
          normalizeWeights(state.weights),
          20,
          state.site,
          u.system,
        ),
        runSitePlan(state.spec, state.site, false, u.system),
        pause(MIN_EXPLORE_MS),
      ]);
      setResults(optimizeRes.results);
      setSoft(optimizeRes.soft);
      setGate(optimizeRes.gate);
      setViewResults(true);
      setSiteData({
        layout: siteRes.layout,
        svg: siteRes.svg,
        concept: siteRes.concept_render_b64,
      });
    } catch (e) {
      setError(errorInfo(e, "Something went wrong"));
      setResults(null);
      setSiteData(null);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDownloadReport() {
    if (!lastState) return;
    setDownloadingReport(true);
    try {
      const { pdf_b64 } = await runReport(
        lastState.spec,
        normalizeWeights(lastState.weights),
        lastState.site,
        0,
        u.system,
      );
      downloadPdf(pdf_b64, "enerzen-feasibility-report.pdf");
    } catch (e) {
      setError(errorInfo(e, "Report generation failed"));
    } finally {
      setDownloadingReport(false);
    }
  }

  async function handleDownloadDevReport() {
    if (!lastDevSpec || !devMixes) return;
    setDownloadingDevReport(true);
    setDevError(null);
    try {
      const { pdf_b64 } = await runDevReport(lastDevSpec, approvedMixes, devMixes[selectedMix].units, u.system);
      downloadPdf(pdf_b64, "enerzen-development-feasibility-report.pdf");
    } catch (e) {
      setDevError(errorInfo(e, "Report generation failed"));
    } finally {
      setDownloadingDevReport(false);
    }
  }

  async function handleDevSubmit(spec: DevSpecInput) {
    if (devIterations >= 3) {
      setDevError({ message: "The site plan review is limited to 3 iterations. Approve a scenario to continue." });
      return;
    }
    setDevPhase("scenarios");
    setDevSubmitting(true);
    setDevError(null);
    setDevSvg(null);
    setDevConcept(null);
    setLastDevSpec(spec);
    try {
      const minimum = pause(MIN_EXPLORE_MS);
      const { scenarios: found, excluded_types, zoning } = await runDevScenarios(spec);
      const { svg } = await runDevSitePlan(spec, found[0].units, false, u.system);
      await minimum;
      setScenarios(found);
      setExcludedTypes(excluded_types ?? []);
      setZoningNotes(zoning ?? []);
      setApproved(found.map(() => true));
      setSelectedScenario(0);
      setDevSvg(svg);
      setDevIterations((count) => count + 1);
      setDevStage("review");
      setViewResults(true);
    } catch (e) {
      setDevError(errorInfo(e, "Something went wrong"));
    } finally {
      setDevSubmitting(false);
    }
  }

  async function showDevPlan(units: Record<string, number>, render: boolean) {
    if (!lastDevSpec || devSubmitting) return false;
    setDevSubmitting(true);
    setDevError(null);
    try {
      const { svg, concept_render_b64 } = await runDevSitePlan(lastDevSpec, units, render, u.system);
      setDevSvg(svg);
      setDevConcept(concept_render_b64);
      return true;
    } catch {
      setDevError({ message: "This site view could not be generated. Please try again." });
      return false;
    } finally {
      setDevSubmitting(false);
    }
  }

  async function handleScenarioSelect(i: number) {
    if (scenarios && (await showDevPlan(scenarios[i].units, false))) setSelectedScenario(i);
  }

  async function handleMixSelect(i: number) {
    if (devMixes && (await showDevPlan(devMixes[i].units, true))) setSelectedMix(i);
  }

  async function handleApprove() {
    if (!lastDevSpec || !scenarios) return;
    const mixes = scenarios.filter((_, i) => approved[i]).map((scenario) => scenario.units);
    if (mixes.length === 0) {
      setDevError({ message: "Tick at least one scenario to carry into performance optimization." });
      return;
    }
    setDevPhase("performance");
    setDevSubmitting(true);
    setDevError(null);
    setViewResults(false);
    try {
      const minimum = pause(MIN_EXPLORE_MS);
      const evaluated = await runDevOptimize(lastDevSpec, mixes);
      const { svg, concept_render_b64 } = await runDevSitePlan(lastDevSpec, evaluated.mixes[0].units, true, u.system);
      await minimum;
      setDevMixes(evaluated.mixes);
      setApprovedMixes(mixes);
      setRejectedMixes(evaluated.rejected);
      setSoftFraction(evaluated.soft_cost_fraction);
      setSelectedMix(0);
      setDevSvg(svg);
      setDevConcept(concept_render_b64);
      setDevStage("final");
    } catch (e) {
      setDevError(errorInfo(e, "Something went wrong"));
    } finally {
      setDevSubmitting(false);
      setViewResults(true);
    }
  }

  async function backToReview() {
    setDevStage("review");
    setDevConcept(null);
    if (scenarios) await showDevPlan(scenarios[selectedScenario].units, false);
  }

  // The API draws a plan in one unit system, so the plans on screen are redrawn
  // when it changes. A failed redraw leaves the plan in its previous units.
  function changeUnits(system: UnitSystem) {
    if (system === u.system) return;
    setUnitSystem(system);
    if (lastState && siteData) {
      runSitePlan(lastState.spec, lastState.site, false, system)
        .then(({ svg }) => setSiteData((data) => data && { ...data, svg }))
        .catch(() => {});
    }
    const mix = devStage === "final" ? devMixes?.[selectedMix]?.units : scenarios?.[selectedScenario]?.units;
    if (lastDevSpec && devSvg && mix) {
      runDevSitePlan(lastDevSpec, mix, false, system)
        .then(({ svg }) => setDevSvg(svg))
        .catch(() => {});
    }
  }

  const busy = submitting || devSubmitting;
  const exploring = busy && !viewResults && (screen === "single" || screen === "development");
  // Errors naming a field of the visible form are shown at that field instead.
  const atField = (e: FieldError | null, steps: Record<string, number>) => !!e?.field && e.field in steps;
  const pageError =
    screen === "single"
      ? !viewResults && atField(error, PROJECT_FIELD_STEP) ? null : error
      : devStage === "brief" && atField(devError, DEV_FIELD_STEP) ? null : devError;
  const exploringContext: ExploringContext =
    screen === "single"
      ? {
          place: placeName(lastState?.spec.location),
          target: targetName(lastState?.spec.target_label),
          brief: lastState
            ? `${lastState.spec.typology.replace("_", " ")}, ${u.area(lastState.spec.floor_area_m2)} over ${lastState.spec.storeys} storeys`
            : "Your home",
          site: lastState ? `a ${u.dims(lastState.site.lot_width_m, lastState.site.lot_depth_m)} lot` : "your lot",
          parcel: lastState?.site.latitude != null,
        }
      : {
          place: placeName(lastDevSpec?.location),
          target: targetName(lastDevSpec?.target_label),
          brief: lastDevSpec
            ? `${lastDevSpec.allowed_types.length} housing types, $${(lastDevSpec.total_budget_cad / 1_000_000).toFixed(2)}M budget`
            : "Your community",
          site: lastDevSpec
            ? `A ${u.dims(lastDevSpec.lot_width_m, lastDevSpec.lot_depth_m)} lot with ${u.length(lastDevSpec.front_setback_m)} front and ${u.length(lastDevSpec.rear_setback_m)} rear setbacks`
            : "Your land",
          parcel: lastDevSpec?.latitude != null,
        };
  const headingCopy =
    screen === "single"
      ? {
          eyebrow: "Your project, in perspective",
          title: "A direction worth exploring.",
          description: "Explore the options, then revisit your brief to refine the direction.",
        }
      : devStage === "final"
        ? {
            eyebrow: "Recommended solution",
            title: "Your recommended community.",
            description: "Building performance optimized for the approved scenarios, then ranked by your priorities.",
          }
        : {
            eyebrow: `Site plan review · ${Math.min(devIterations, 3)} of 3`,
            title: "Review the site plans.",
            description: "Approve the scenarios worth optimizing, or revise the brief and generate new plans.",
          };
  const choose = (path: Screen) => {
    setScreen(path);
    setViewResults(false);
  };
  return (
    <div className="enerzen-app">
      <div className="ambient" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="app-header">
        <button
          className="wordmark"
          disabled={busy}
          onClick={() => choose("welcome")}
          aria-label="EnerZen home"
        >
          <img src="/brand/enerzen-logo.svg" alt="" aria-hidden="true" />
        </button>
        <nav aria-label="Main navigation">
          <div className="unit-toggle" role="group" aria-label="Units">
            {(["imperial", "metric"] as const).map((system) => (
              <button
                key={system}
                type="button"
                disabled={busy}
                aria-pressed={u.system === system}
                aria-label={system === "imperial" ? "Imperial units" : "Metric units"}
                onClick={() => changeUnits(system)}
              >
                <span className="unit-long">{system === "imperial" ? "Imperial" : "Metric"}</span>
                <span className="unit-short">{system === "imperial" ? "ft" : "m"}</span>
              </button>
            ))}
          </div>
          <span className="pilot-chip">
            <span /> Pickering pilot
          </span>
          {screen !== "welcome" && (
            <button
              className="quiet-button"
              disabled={busy}
              onClick={() => choose(screen === "path" ? "welcome" : "path")}
            >
              {screen === "path" ? "Back to home" : "Change path"}{" "}
              <span aria-hidden="true">↗</span>
            </button>
          )}
          {screen === "welcome" && (
            <button className="quiet-button" onClick={() => choose("path")}>
              Open workspace <span aria-hidden="true">↗</span>
            </button>
          )}
        </nav>
      </header>

      {screen === "welcome" && (
        <main id="main-content" className="landing">
          <section className="hero animate-screen-in">
            <div className="hero-copy">
              <p className="micro-label">
                <span className="status-dot" /> AI-powered early planning
              </p>
              <h1
                ref={heading}
                tabIndex={-1}
                aria-label="Intelligent housing. Powered by AI. Built for tomorrow."
              >
                <span className="hero-title-line" aria-hidden="true">
                  <span className="word-reveal">Intelligent housing.</span>
                </span>
                <span
                  className="hero-title-line muted-title"
                  aria-hidden="true"
                >
                  <span
                    className="word-reveal"
                    style={{ animationDelay: "160ms" }}
                  >
                    Powered by AI.
                  </span>
                </span>
                <span
                  className="hero-title-line muted-title"
                  aria-hidden="true"
                >
                  <span
                    className="word-reveal"
                    style={{ animationDelay: "240ms" }}
                  >
                    Built for tomorrow.
                  </span>
                </span>
              </h1>
              <p className="hero-description description-reveal">
                Compare home designs and housing mixes against your site rules,
                budget, energy and carbon goals before committing to design.
              </p>
              <div className="hero-actions">
                <button
                  className="primary-button"
                  onClick={() => choose("path")}
                >
                  Start your project <span aria-hidden="true">↗</span>
                </button>
                <a className="text-link" href="#approach">
                  See how it works <span aria-hidden="true">↓</span>
                </a>
              </div>
              <div className="hero-note">
                <span className="fine-line" /> Designed for early decisions.
                Built around your priorities.
              </div>
            </div>
            <div
              className="hero-art"
              aria-label="Architectural illustration of a courtyard community"
            >
              <div className="art-topline">
                <span>THE BIGGER PICTURE</span>
                <span>01 — EXPLORATION</span>
              </div>
              <Architecture />
              <div className="art-caption">
                <span>
                  <i /> Space for a better future.
                </span>
                <span>Concept illustration</span>
              </div>
            </div>
          </section>
          <section id="approach" className="approach">
            <div>
              <p className="micro-label">Consider more. Decide better.</p>
              <h2>
                One place to see
                <br />
                how it all connects.
              </h2>
            </div>
            {[
              [
                "01",
                "Start with a place.",
                "Explore Pickering’s local context. A specific address can come later.",
              ],
              [
                "02",
                "Shape the possibilities.",
                "Choose housing, systems and the trade-offs that matter to you.",
              ],
              [
                "03",
                "See the whole picture.",
                "Compare site fit, energy, cost and carbon in a shared recommendation.",
              ],
            ].map(([n, title, text]) => (
              <article key={n}>
                <span className="micro-label">{n}</span>
                <h3>{title}</h3>
                <p>{text}</p>
              </article>
            ))}
          </section>
        </main>
      )}

      {screen === "path" && (
        <main id="main-content" className="path-page animate-screen-in">
          <div className="page-intro">
            <p className="micro-label">Your next possibility</p>
            <h1 ref={heading} tabIndex={-1}>
              What are we creating?
            </h1>
            <p>Two ways to begin. The same thoughtful approach.</p>
          </div>
          <div className="path-grid">
            <WorkflowCard
              eyebrow="01 / INDIVIDUAL UNIT"
              title="A place to call home."
              description="Bring one home into focus. Explore its design, site fit and performance, one decision at a time."
              items={[
                "Project & site",
                "Design & systems",
                "Performance & recommendation",
              ]}
              onClick={() => choose("single")}
            />
            <WorkflowCard
              eyebrow="02 / COMMUNITY DEVELOPMENT"
              title="Room for a community."
              description="Think beyond a single building. Explore a housing mix, shared spaces and the life between them."
              items={[
                "Land & planning",
                "Housing mix & priorities",
                "Site plan & scenarios",
              ]}
              onClick={() => choose("development")}
            />
          </div>
          <p className="path-footnote">
            <span className="status-dot" /> Starting in Pickering, Ontario. No
            address needed to explore.
          </p>
        </main>
      )}

      <main
        id={
          screen === "single" || screen === "development"
            ? "main-content"
            : undefined
        }
        className="workspace"
        hidden={screen !== "single" && screen !== "development"}
      >
        <div className="workspace-top">
          <span className="micro-label">
            Workspace /{" "}
            {screen === "single" ? "Individual unit" : "Community development"}
          </span>
          <span className="micro-label">Ontario, Canada</span>
        </div>
        <div hidden={screen !== "single" || viewResults || exploring}>
          <ProjectForm
            key={lot ? `${lot.latitude},${lot.longitude}` : "blank"}
            initialSite={lot}
            onSubmit={handleSingleSubmit}
            submitting={submitting}
            error={error}
          />
        </div>
        <div hidden={screen !== "development" || viewResults || exploring}>
          <DevForm
            onSubmit={handleDevSubmit}
            submitting={devSubmitting}
            iteration={devIterations}
            error={devStage === "brief" ? devError : null}
          />
        </div>
        {exploring && (
          <ExploringStage
            path={screen === "single" ? "single" : devPhase === "scenarios" ? "dev-scenarios" : "dev-performance"}
            context={exploringContext}
          />
        )}
        {/* Errors naming a form field are shown at that field instead. */}
        {pageError && (
          <div role="alert" className="error-message">
            {pageError.message}
            {pageError.fix && <span className="block">{pageError.fix}</span>}
          </div>
        )}
        {busy && viewResults && (
          <div className="processing-message" role="status">
            <span className="loading-orbit" />
            <div>
              <strong>Redrawing the site plan</strong>
              <p>Placing the selected mix with its walkway, entrances, parking and shared green.</p>
            </div>
          </div>
        )}
        {viewResults && (
          <section className="results-workspace results-reveal">
            <div className="results-heading">
              <div>
                <p className="micro-label reveal-item" style={at(0)}>
                  {headingCopy.eyebrow}
                </p>
                <h1 ref={heading} tabIndex={-1} aria-label={headingCopy.title}>
                  {headingCopy.title.split(" ").map((word, index) => (
                    <span
                      aria-hidden="true"
                      className="word-reveal"
                      key={`${headingCopy.title}-${index}`}
                      style={{ animationDelay: `${120 + index * 90}ms` }}
                    >
                      {word}{" "}
                    </span>
                  ))}
                </h1>
                <p className="reveal-item" style={at(0.55)}>
                  {headingCopy.description}
                </p>
              </div>
              {screen === "development" && devStage === "final" ? (
                <button className="secondary-button reveal-item" style={at(0.7)} disabled={busy} onClick={backToReview}>
                  ← Back to site plan review
                </button>
              ) : (
                <button
                  className="secondary-button reveal-item"
                  style={at(0.7)}
                  disabled={busy || (screen === "development" && devIterations >= 3)}
                  onClick={() => setViewResults(false)}
                >
                  {screen === "development"
                    ? devIterations >= 3
                      ? "Review limit reached"
                      : `← Revise brief (${3 - devIterations} left)`
                    : "← Edit project brief"}
                </button>
              )}
            </div>
            {screen === "single" && results && (
              <>
                <div className="result-toolbar reveal-item" style={at(0.85)}>
                  <span className="micro-label">
                    {gate
                      ? `${gate.evaluated.toLocaleString()} evaluated · ${gate.passed.toLocaleString()} passed · ${gate.over_budget.toLocaleString()} over budget · ${gate.missed_target.toLocaleString()} missed the target`
                      : `Top ${results.length} configurations that passed the gate`}
                  </span>
                  <button
                    className="secondary-button"
                    onClick={handleDownloadReport}
                    disabled={downloadingReport}
                  >
                    {downloadingReport
                      ? "Preparing report…"
                      : "Download feasibility report ↓"}
                  </button>
                </div>
                <ResultsPanel results={results} soft={soft} />
                {siteData && (
                  <div className="reveal-item reveal-plan" style={at(2.3)}>
                    <SitePlanView
                      svg={siteData.svg}
                      layout={siteData.layout}
                      conceptRenderB64={siteData.concept}
                    />
                  </div>
                )}
              </>
            )}
            {screen === "development" && devStage === "review" && scenarios && (
              <>
                <div className="review-actions reveal-item" style={at(0.85)}>
                  <p>
                    <strong>{approved.filter(Boolean).length}</strong> of {scenarios.length} scenarios selected for
                    building performance optimization.
                  </p>
                  <button className="primary-button" disabled={busy} onClick={handleApprove}>
                    Approve and optimize <span aria-hidden="true">↗</span>
                  </button>
                </div>
                <div className="review-grid">
                  <div className="reveal-item" style={at(1)}>
                    <DevScenarioReview
                      excluded={excludedTypes}
                      zoning={zoningNotes}
                      scenarios={scenarios}
                      selectedIndex={selectedScenario}
                      approved={approved}
                      onSelect={handleScenarioSelect}
                      onToggle={(i) => setApproved((current) => current.map((value, j) => (j === i ? !value : value)))}
                    />
                  </div>
                  {devSvg && scenarios[selectedScenario] && (
                    <div className="reveal-item reveal-plan" style={at(1.4)}>
                      <MultiSitePlanView
                        svg={devSvg}
                        eyebrow={`Scenario ${selectedScenario + 1} · 2D site plan`}
                        title={scenarios[selectedScenario].mix_label}
                        conceptRenderB64={null}
                        stats={[
                          { label: "Homes", value: String(scenarios[selectedScenario].dwellings) },
                          { label: "Built area", value: u.area(scenarios[selectedScenario].total_floor_area_m2) },
                          {
                            label: "Site coverage",
                            value: `${Math.round(scenarios[selectedScenario].site_coverage * 100)}%`,
                            tip: "Building footprint as a share of the lot.",
                          },
                          {
                            label: "From cost",
                            value: fmtCad(scenarios[selectedScenario].screening_cost),
                            tip: "Cheapest catalog configuration before performance optimization; a floor, not an estimate.",
                          },
                        ]}
                      />
                    </div>
                  )}
                </div>
              </>
            )}
            {screen === "development" && devStage === "final" && devMixes && devMixes.length > 0 && (
              <>
                <div className="result-toolbar reveal-item" style={at(0.85)}>
                  <span className="micro-label">
                    Report for {selectedMix === 0 ? "the recommended mix" : devMixes[selectedMix].mix_label}
                  </span>
                  <button
                    className="secondary-button"
                    onClick={handleDownloadDevReport}
                    disabled={downloadingDevReport || devSubmitting}
                  >
                    {downloadingDevReport ? "Preparing report…" : "Download feasibility report ↓"}
                  </button>
                </div>
                <div className="reveal-item" style={at(0.85)}>
                  <DevRecommendation mix={devMixes[0]} softFraction={softFraction} />
                </div>
                <div className="results-table reveal-item" style={at(1.5)}>
                  <DevResults mixes={devMixes} selectedIndex={selectedMix} onSelect={handleMixSelect} />
                </div>
                {rejectedMixes.length > 0 && (
                  <div className="rejected-list reveal-item" style={at(1.8)}>
                    <p className="micro-label">Set aside by the gate</p>
                    <ul>
                      {rejectedMixes.map((mix) => (
                        <li key={mix.mix_label}>
                          <strong>{mix.mix_label}</strong> {mix.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {devSvg && devMixes[selectedMix] && (
                  <div className="reveal-item reveal-plan" style={at(2.1)}>
                    <MultiSitePlanView
                      svg={devSvg}
                      eyebrow={selectedMix === 0 ? "Recommended · 2D site plan" : `Rank ${selectedMix + 1} · 2D site plan`}
                      title={devMixes[selectedMix].mix_label}
                      conceptRenderB64={devConcept}
                      stats={[
                        { label: "Homes", value: String(devMixes[selectedMix].total_units) },
                        { label: "Project cost", value: fmtCad(devMixes[selectedMix].total_project_cost) },
                        { label: "Avg EUI", value: u.eui(devMixes[selectedMix].avg_eui_kwh_m2_yr) },
                        {
                          label: "NZR homes",
                          value: `${devMixes[selectedMix].nzr_unit_count}/${devMixes[selectedMix].total_units}`,
                          tone: devMixes[selectedMix].nzr_unit_count === devMixes[selectedMix].total_units ? "good" : "warn",
                        },
                        { label: "Utility / home", value: `${fmtCad(devMixes[selectedMix].avg_monthly_utility)}/mo` },
                      ]}
                    />
                  </div>
                )}
              </>
            )}
          </section>
        )}
      </main>
      <footer className="app-footer">
        <span>
          <img src="/brand/enerzen-symbol.svg" alt="" aria-hidden="true" /> Enerzen <span className="footer-divider">/</span> Thoughtful by
          design.
        </span>
        <span>
          Early-stage housing feasibility{" "}
          <span className="footer-divider">·</span> Pickering, ON
        </span>
      </footer>
    </div>
  );
}

function WorkflowCard({
  eyebrow,
  title,
  description,
  items,
  onClick,
}: {
  eyebrow: string;
  title: string;
  description: string;
  items: string[];
  onClick: () => void;
}) {
  return (
    <button type="button" className="path-card" onClick={onClick}>
      <div className="path-card-top">
        <span className="micro-label">{eyebrow}</span>
        <span className="circle-arrow" aria-hidden="true">
          ↗
        </span>
      </div>
      <div className="path-icon" aria-hidden="true">
        <svg
          viewBox="0 0 100 72"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
        >
          {eyebrow.startsWith("01") ? (
            <>
              <path d="M20 32 50 13 80 32v32H20Z" />
              <path d="M50 13v51M20 32l30 18 30-18M35 64V43M65 64V43" />
            </>
          ) : (
            <>
              <path d="m8 35 20-12 20 12v26H8ZM48 35l22-14 22 14v26H48ZM30 22 50 10l20 11M28 23v38M70 21v40" />
              <path d="M8 35l20 12 20-12 22 14 22-14" />
            </>
          )}
        </svg>
      </div>
      <h2>{title}</h2>
      <p>{description}</p>
      <div className="path-card-steps">
        {items.map((item, i) => (
          <span key={item}>
            <small>0{i + 1}</small>
            {item}
          </span>
        ))}
      </div>
      <span className="path-card-cta">
        Explore this path <span aria-hidden="true">→</span>
      </span>
    </button>
  );
}

function normalizeWeights(weights: FormState["weights"]): FormState["weights"] {
  const total = Object.values(weights).reduce((sum, value) => sum + value, 0);
  if (total === 0)
    return { cost: 0.25, speed: 0.25, carbon: 0.25, energy: 0.25 };
  return Object.fromEntries(
    Object.entries(weights).map(([key, value]) => [key, value / total]),
  ) as FormState["weights"];
}

function placeName(location: string | null | undefined): string {
  return (location ?? "Ontario").replace(" (Dunbarton)", "");
}

function targetName(label: string | undefined): string {
  return label === "passive_house" ? "Passive House" : label === "nzr" ? "Net Zero Ready" : "code minimum";
}

function downloadPdf(b64: string, filename: string) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
