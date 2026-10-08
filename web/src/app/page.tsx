"use client";

import { useState, useEffect, useRef, type CSSProperties } from "react";
import ProjectForm, { FormState } from "@/components/ProjectForm";
import ResultsPanel from "@/components/ResultsPanel";
import SitePlanView from "@/components/SitePlanView";
import DevForm from "@/components/DevForm";
import DevResults from "@/components/DevResults";
import MultiSitePlanView from "@/components/MultiSitePlanView";
import Architecture from "@/components/Architecture";
import ExploringStage, { type ExploringContext } from "@/components/ExploringStage";
import {
  ConfigResult,
  SiteLayout,
  runOptimize,
  runReport,
  runSitePlan,
  DevSpecInput,
  DevMixResult,
  runDevOptimize,
  runDevSitePlan,
} from "@/lib/api";

type Screen = "welcome" | "path" | "single" | "development";

// Long enough to read the first few narrated stages when the engine is fast.
const MIN_EXPLORE_MS = 2600;
const pause = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));
// Delay for one step of the staged results reveal.
const at = (seconds: number) => ({ "--d": `${seconds}s` }) as CSSProperties;

export default function Home() {
  const [screen, setScreen] = useState<Screen>("welcome");

  const [viewResults, setViewResults] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    window.scrollTo({ top: 0 });
    heading.current?.focus();
  }, [screen, viewResults]);

  // ── Single-unit state ──────────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<ConfigResult[] | null>(null);
  const [siteData, setSiteData] = useState<{
    layout: SiteLayout;
    svg: string;
    concept: string | null;
  } | null>(null);
  const [lastState, setLastState] = useState<FormState | null>(null);
  const [downloadingReport, setDownloadingReport] = useState(false);

  // ── Development-plan state ─────────────────────────────────────────────────
  const [devSubmitting, setDevSubmitting] = useState(false);
  const [devError, setDevError] = useState<string | null>(null);
  const [devMixes, setDevMixes] = useState<DevMixResult[] | null>(null);
  const [devSvg, setDevSvg] = useState<string | null>(null);
  const [devConcept, setDevConcept] = useState<string | null>(null);
  const [selectedMix, setSelectedMix] = useState(0);
  const [lastDevSpec, setLastDevSpec] = useState<DevSpecInput | null>(null);
  const [devIterations, setDevIterations] = useState(0);

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
        ),
        runSitePlan(state.spec, state.site),
        pause(MIN_EXPLORE_MS),
      ]);
      setResults(optimizeRes.results);
      setViewResults(true);
      setSiteData({
        layout: siteRes.layout,
        svg: siteRes.svg,
        concept: siteRes.concept_render_b64,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
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
      );
      const bytes = Uint8Array.from(atob(pdf_b64), (c) => c.charCodeAt(0));
      const blob = new Blob([bytes], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "enerzen-project-report.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Report generation failed");
    } finally {
      setDownloadingReport(false);
    }
  }

  async function handleDevSubmit(spec: DevSpecInput) {
    if (devIterations >= 3) {
      setDevError(
        "The development review loop is limited to 3 iterations. Start a new session to continue.",
      );
      return;
    }
    setDevSubmitting(true);
    setDevError(null);
    setDevSvg(null);
    setDevConcept(null);
    setLastDevSpec(spec);
    setSelectedMix(0);
    try {
      const minimum = pause(MIN_EXPLORE_MS);
      const { mixes } = await runDevOptimize(spec);
      setDevMixes(mixes);
      if (mixes.length > 0) {
        const { svg, concept_render_b64 } = await runDevSitePlan(
          spec,
          mixes[0].units,
          true,
        );
        setDevSvg(svg);
        setDevConcept(concept_render_b64);
      }
      await minimum;
      setDevIterations((count) => count + 1);
      setViewResults(true);
    } catch (e) {
      setDevError(e instanceof Error ? e.message : "Something went wrong");
      setDevMixes(null);
      setDevSvg(null);
      setDevConcept(null);
    } finally {
      setDevSubmitting(false);
    }
  }

  async function handleMixSelect(i: number) {
    if (!lastDevSpec || !devMixes) return;
    if (devSubmitting) return;
    setDevSubmitting(true);
    setDevError(null);
    try {
      const { svg, concept_render_b64 } = await runDevSitePlan(
        lastDevSpec,
        devMixes[i].units,
        true,
      );
      setSelectedMix(i);
      setDevSvg(svg);
      setDevConcept(concept_render_b64);
    } catch {
      setDevError("This site view could not be generated. Please try again.");
    } finally {
      setDevSubmitting(false);
    }
  }

  const busy = submitting || devSubmitting;
  const exploring = busy && !viewResults && (screen === "single" || screen === "development");
  const exploringContext: ExploringContext =
    screen === "single"
      ? {
          place: placeName(lastState?.spec.location),
          target: targetName(lastState?.spec.target_label),
          brief: lastState
            ? `${lastState.spec.typology.replace("_", " ")}, ${lastState.spec.floor_area_m2} m² over ${lastState.spec.storeys} storeys`
            : "Your home",
          site: lastState ? `a ${lastState.site.lot_width_m} × ${lastState.site.lot_depth_m} m lot` : "your lot",
        }
      : {
          place: placeName(lastDevSpec?.location),
          target: targetName(lastDevSpec?.target_label),
          brief: lastDevSpec
            ? `${lastDevSpec.allowed_types.length} housing types, $${(lastDevSpec.total_budget_cad / 1_000_000).toFixed(2)}M budget`
            : "Your community",
          site: lastDevSpec
            ? `A ${lastDevSpec.lot_width_m} × ${lastDevSpec.lot_depth_m} m lot with ${lastDevSpec.front_setback_m} m front and ${lastDevSpec.rear_setback_m} m rear setbacks`
            : "Your land",
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
          <span className="brand-symbol" aria-hidden="true">
            e
          </span>
          enerzen
          <span className="brand-dot" aria-hidden="true">
            •
          </span>
        </button>
        <nav aria-label="Main navigation">
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
                <span className="status-dot" /> A clearer way to build
              </p>
              <h1
                ref={heading}
                tabIndex={-1}
                aria-label="Good places. Better possibilities."
              >
                <span className="hero-title-line" aria-hidden="true">
                  <span className="word-reveal">Good </span>
                  <span
                    className="word-reveal"
                    style={{ animationDelay: "80ms" }}
                  >
                    places.
                  </span>
                </span>
                <span
                  className="hero-title-line muted-title"
                  aria-hidden="true"
                >
                  <span
                    className="word-reveal"
                    style={{ animationDelay: "160ms" }}
                  >
                    Better{" "}
                  </span>
                  <span
                    className="word-reveal"
                    style={{ animationDelay: "240ms" }}
                  >
                    possibilities.
                  </span>
                </span>
              </h1>
              <p className="hero-description description-reveal">
                From the first idea to a more thoughtful home or community.
                Explore the space between what you imagine and what your site
                can become.
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
          <ProjectForm onSubmit={handleSingleSubmit} submitting={submitting} />
        </div>
        <div hidden={screen !== "development" || viewResults || exploring}>
          <DevForm
            onSubmit={handleDevSubmit}
            submitting={devSubmitting}
            iteration={devIterations}
          />
        </div>
        {exploring && (
          <ExploringStage
            path={screen === "single" ? "single" : "development"}
            context={exploringContext}
          />
        )}
        {(screen === "single" ? error : devError) && (
          <div role="alert" className="error-message">
            {screen === "single" ? error : devError}
          </div>
        )}
        {busy && viewResults && (
          <div className="processing-message" role="status">
            <span className="loading-orbit" />
            <div>
              <strong>Redrawing the site plan</strong>
              <p>Placing the selected mix and its walkway, parking and shared green.</p>
            </div>
          </div>
        )}
        {viewResults && (
          <section className="results-workspace results-reveal">
            <div className="results-heading">
              <div>
                <p className="micro-label reveal-item" style={at(0)}>
                  Your project, in perspective
                </p>
                <h1
                  ref={heading}
                  tabIndex={-1}
                  aria-label={screen === "single" ? "A direction worth exploring." : "The shape of your community."}
                >
                  {(screen === "single" ? "A direction worth exploring." : "The shape of your community.")
                    .split(" ")
                    .map((word, index) => (
                      <span
                        aria-hidden="true"
                        className="word-reveal"
                        key={index}
                        style={{ animationDelay: `${120 + index * 90}ms` }}
                      >
                        {word}{" "}
                      </span>
                    ))}
                </h1>
                <p className="reveal-item" style={at(0.55)}>
                  Explore the options, then revisit your brief to refine the direction.
                </p>
              </div>
              <button
                className="secondary-button reveal-item"
                style={at(0.7)}
                disabled={busy}
                onClick={() => setViewResults(false)}
              >
                ← Edit project brief
              </button>
            </div>
            {screen === "single" && results && (
              <>
                <div className="result-toolbar reveal-item" style={at(0.85)}>
                  <span className="micro-label">
                    Top {results.length} configurations that passed the gate
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
                <ResultsPanel results={results} />
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
            {screen === "development" && devMixes && (
              <>
                {devMixes.length === 0 ? (
                  <div className="empty-state reveal-item" style={at(0.85)}>
                    <h2>No feasible mix yet.</h2>
                    <p>
                      Try adjusting the budget, lot dimensions or housing types
                      in your brief.
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="results-table reveal-item" style={at(0.9)}>
                      <DevResults
                        mixes={devMixes}
                        selectedIndex={selectedMix}
                        onSelect={handleMixSelect}
                      />
                    </div>
                    {devSvg && devMixes[selectedMix] && (
                      <div className="reveal-item reveal-plan" style={at(1.9)}>
                        <MultiSitePlanView
                          svg={devSvg}
                          mix={devMixes[selectedMix]}
                          conceptRenderB64={devConcept}
                        />
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </section>
        )}
      </main>
      <footer className="app-footer">
        <span>
          enerzen <span className="footer-divider">/</span> Thoughtful by
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
