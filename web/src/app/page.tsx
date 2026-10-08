"use client";

import { useState } from "react";
import ProjectForm, { FormState } from "@/components/ProjectForm";
import ResultsPanel from "@/components/ResultsPanel";
import SitePlanView from "@/components/SitePlanView";
import DevForm from "@/components/DevForm";
import DevResults from "@/components/DevResults";
import MultiSitePlanView from "@/components/MultiSitePlanView";
import {
  ConfigResult, SiteLayout,
  runOptimize, runReport, runSitePlan,
  DevSpecInput, DevMixResult,
  runDevOptimize, runDevSitePlan,
} from "@/lib/api";

type Screen = "welcome" | "path" | "single" | "development";

export default function Home() {
  const [screen, setScreen] = useState<Screen>("welcome");

  // ── Single-unit state ──────────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<ConfigResult[] | null>(null);
  const [siteData, setSiteData] = useState<{ layout: SiteLayout; svg: string; concept: string | null } | null>(null);
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
        runOptimize(state.spec, normalizeWeights(state.weights), 20, state.site),
        runSitePlan(state.spec, state.site),
      ]);
      setResults(optimizeRes.results);
      setSiteData({ layout: siteRes.layout, svg: siteRes.svg, concept: siteRes.concept_render_b64 });
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
      setDevError("The development review loop is limited to 3 iterations. Start a new session to continue.");
      return;
    }
    setDevSubmitting(true);
    setDevError(null);
    setDevIterations((count) => count + 1);
    setLastDevSpec(spec);
    setSelectedMix(0);
    try {
      const { mixes } = await runDevOptimize(spec);
      setDevMixes(mixes);
      if (mixes.length > 0) {
        const { svg, concept_render_b64 } = await runDevSitePlan(spec, mixes[0].units, true);
        setDevSvg(svg);
        setDevConcept(concept_render_b64);
      }
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
    setSelectedMix(i);
    try {
      const { svg, concept_render_b64 } = await runDevSitePlan(lastDevSpec, devMixes[i].units, true);
      setDevSvg(svg);
      setDevConcept(concept_render_b64);
    } catch {
      // keep existing svg
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen overflow-hidden bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.18),transparent_34rem),linear-gradient(135deg,#f8faf5_0%,#eef3eb_48%,#f9faf7_100%)]">
      <header className="sticky top-0 z-20 border-b border-white/70 bg-white/75 px-5 py-3 shadow-sm backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-900 text-sm font-bold text-white shadow-lg shadow-emerald-900/15">
              EZ
            </div>
            <div>
              <h1 className="text-base font-semibold text-stone-950">EnerZen Performance Engine</h1>
              <p className="text-xs text-stone-500">
                Envelope, energy, carbon, and site fit for Ontario housing
              </p>
            </div>
          </div>

          {screen !== "welcome" && (
            <button
              onClick={() => setScreen(screen === "path" ? "welcome" : "path")}
              className="rounded-lg border border-stone-200 bg-white/80 px-4 py-2 text-xs font-semibold text-stone-600 shadow-sm transition hover:border-emerald-300 hover:text-emerald-800"
            >
              {screen === "path" ? "Back to welcome" : "Change workflow"}
            </button>
          )}
        </div>
      </header>

      {screen === "welcome" && (
        <main className="mx-auto max-w-6xl px-5 py-10 sm:py-16">
          <section className="grid items-center gap-10 rounded-3xl border border-white/80 bg-white/75 p-7 shadow-xl shadow-emerald-950/5 sm:p-12 lg:grid-cols-[1.1fr_0.9fr]">
            <div>
              <p className="eyebrow">EnerZen early-stage feasibility</p>
              <h2 className="mt-4 max-w-2xl text-4xl font-semibold tracking-tight text-stone-950 sm:text-6xl">
                Make better housing decisions before design gets expensive.
              </h2>
              <p className="mt-5 max-w-xl text-base leading-7 text-stone-600">
                Explore high-performance homes and sustainable community development options using EnerZen&apos;s catalog, energy engine, cost model, and site intelligence.
              </p>
              <button
                type="button"
                onClick={() => setScreen("path")}
                className="mt-8 rounded-xl bg-emerald-900 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-emerald-900/20 transition hover:-translate-y-0.5 hover:bg-emerald-800"
              >
                Start with EnerZen
              </button>
            </div>
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50/80 p-6">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-800">What EnerZen evaluates</p>
              <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
                {["Capital cost", "Energy performance", "Embodied + lifecycle carbon", "Site fit and development potential"].map((item) => (
                  <div key={item} className="rounded-xl border border-emerald-100 bg-white/80 px-4 py-3 text-sm font-medium text-stone-700">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </section>
        </main>
      )}

      {screen === "path" && (
        <main className="mx-auto max-w-5xl px-5 py-10 sm:py-16">
          <section className="text-center">
            <p className="eyebrow">Choose your workflow</p>
            <h2 className="mt-3 text-3xl font-semibold text-stone-950 sm:text-4xl">What are you planning?</h2>
            <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-stone-500">
              Each path has its own questions, analysis, and recommendation sequence. You can return here and explore the other path at any time.
            </p>
          </section>
          <section className="mt-8 grid gap-5 md:grid-cols-2">
            <WorkflowCard
              eyebrow="Path A"
              title="Individual unit"
              description="Evaluate one home, garden suite, townhome, or MURB design against its site, budget, energy target, and building systems."
              items={["Project and site inputs", "Catalog design selection", "Assemblies and mechanical systems", "Performance and feasibility report"]}
              onClick={() => setScreen("single")}
            />
            <WorkflowCard
              eyebrow="Path B"
              title="Community development"
              description="Test a housing mix on a land parcel and develop a sustainable community concept with site planning, yield, cost, energy, and carbon trade-offs."
              items={["Development brief and land inputs", "Planning and site intelligence", "Housing mix scenarios", "2D site plan and community recommendation"]}
              onClick={() => {
                setDevIterations(0);
                setDevError(null);
                setScreen("development");
              }}
            />
          </section>
        </main>
      )}

      {(screen === "single" || screen === "development") && (
      <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-5 py-6 lg:grid-cols-[400px_1fr] lg:items-start">

        {/* ── Single Unit mode ── */}
        {screen === "single" && (
          <>
            <section className="lg:sticky lg:top-24">
              <ProjectForm onSubmit={handleSingleSubmit} submitting={submitting} />
            </section>

            <section className="space-y-6">
              {error && (
                <div className="rounded-xl border border-red-200 bg-red-50/90 p-4 text-sm font-medium text-red-700 shadow-sm">
                  {error}
                </div>
              )}

              {!results && !error && (
                <div className="panel flex min-h-[28rem] items-center justify-center p-8 text-center">
                  <div className="max-w-md">
                    <p className="eyebrow">Ready when you are</p>
                    <h2 className="mt-3 text-3xl font-semibold text-stone-950">
                      Model the best build path in seconds.
                    </h2>
                    <p className="mt-3 text-sm leading-6 text-stone-500">
                      Complete the project inputs to compare construction cost, EUI, lifecycle cost, carbon, and site placement.
                    </p>
                  </div>
                </div>
              )}

              {results && (
                <>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <p className="eyebrow">Optimization result</p>
                      <h2 className="mt-1 text-2xl font-semibold text-stone-950">Best-fit configuration</h2>
                    </div>
                    <button
                      onClick={handleDownloadReport}
                      disabled={downloadingReport}
                      className="rounded-lg border border-stone-200 bg-white px-4 py-2 text-xs font-semibold text-stone-700 shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-200 hover:text-emerald-800 hover:shadow-md disabled:translate-y-0 disabled:opacity-40"
                    >
                      {downloadingReport ? "Generating..." : "Download PDF report"}
                    </button>
                  </div>
                  <ResultsPanel results={results} />
                </>
              )}

              {siteData && (
                <SitePlanView svg={siteData.svg} layout={siteData.layout} conceptRenderB64={siteData.concept} />
              )}
            </section>
          </>
        )}

        {/* ── Development Plan mode ── */}
        {screen === "development" && (
          <>
            <section className="lg:sticky lg:top-24">
              <DevForm
                onSubmit={handleDevSubmit}
                submitting={devSubmitting}
                iteration={devIterations}
              />
            </section>

            <section className="space-y-6">
              {devError && (
                <div className="rounded-xl border border-red-200 bg-red-50/90 p-4 text-sm font-medium text-red-700 shadow-sm">
                  {devError}
                </div>
              )}

              {!devMixes && !devError && (
                <div className="panel flex min-h-[28rem] items-center justify-center p-8 text-center">
                  <div className="max-w-md">
                    <p className="eyebrow">Development planner</p>
                    <h2 className="mt-3 text-3xl font-semibold text-stone-950">
                      Find the best unit mix for your lot.
                    </h2>
                    <p className="mt-3 text-sm leading-6 text-stone-500">
                      Enter your lot dimensions, budget, and preferred unit types.
                      The engine will enumerate feasible configurations and rank them
                      by total units, energy performance, and Net Zero compliance.
                    </p>
                  </div>
                </div>
              )}

              {devMixes && devMixes.length > 0 && (
                <DevResults
                  mixes={devMixes}
                  selectedIndex={selectedMix}
                  onSelect={handleMixSelect}
                />
              )}

              {devSvg && devMixes && devMixes[selectedMix] && (
                <MultiSitePlanView
                  svg={devSvg}
                  mix={devMixes[selectedMix]}
                  conceptRenderB64={devConcept}
                />
              )}
            </section>
          </>
        )}
      </main>
      )}
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
    <button
      type="button"
      onClick={onClick}
      className="group rounded-2xl border border-stone-200 bg-white p-6 text-left shadow-sm transition hover:-translate-y-1 hover:border-emerald-300 hover:shadow-xl hover:shadow-emerald-950/10"
    >
      <p className="eyebrow">{eyebrow}</p>
      <h3 className="mt-2 text-2xl font-semibold text-stone-950">{title}</h3>
      <p className="mt-3 text-sm leading-6 text-stone-500">{description}</p>
      <div className="mt-6 space-y-2 border-t border-stone-100 pt-5">
        {items.map((item) => (
          <div key={item} className="flex items-center gap-2 text-xs font-medium text-stone-600">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-600" />
            {item}
          </div>
        ))}
      </div>
      <span className="mt-7 inline-flex text-xs font-semibold text-emerald-800 transition group-hover:translate-x-1">
        Choose this path →
      </span>
    </button>
  );
}

function normalizeWeights(weights: FormState["weights"]): FormState["weights"] {
  const total = Object.values(weights).reduce((sum, value) => sum + value, 0);
  if (total === 0) {
    return { cost: 0.25, speed: 0.25, carbon: 0.25, energy: 0.25 };
  }
  return Object.fromEntries(
    Object.entries(weights).map(([key, value]) => [key, value / total])
  ) as FormState["weights"];
}
