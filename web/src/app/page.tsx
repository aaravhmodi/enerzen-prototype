"use client";

import { useState } from "react";
import ProjectForm, { FormState } from "@/components/ProjectForm";
import ResultsPanel from "@/components/ResultsPanel";
import SitePlanView from "@/components/SitePlanView";
import { ConfigResult, SiteLayout, runOptimize, runReport, runSitePlan } from "@/lib/api";

export default function Home() {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<ConfigResult[] | null>(null);
  const [siteData, setSiteData] = useState<{ layout: SiteLayout; svg: string; concept: string | null } | null>(null);
  const [lastState, setLastState] = useState<FormState | null>(null);
  const [downloadingReport, setDownloadingReport] = useState(false);

  async function handleSubmit(state: FormState) {
    setSubmitting(true);
    setError(null);
    setLastState(state);
    try {
      const [optimizeRes, siteRes] = await Promise.all([
        runOptimize(state.spec),
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
      const { pdf_b64 } = await runReport(lastState.spec);
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
          <div className="flex items-center gap-2 text-xs font-medium text-stone-500">
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-800">
              Live optimizer
            </span>
            <span className="rounded-full border border-stone-200 bg-white/80 px-3 py-1">
              Net zero ready
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-5 py-6 lg:grid-cols-[400px_1fr] lg:items-start">
        <section className="lg:sticky lg:top-24">
          <ProjectForm onSubmit={handleSubmit} submitting={submitting} />
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
                <h2 className="mt-3 text-3xl font-semibold text-stone-950">Model the best build path in seconds.</h2>
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
      </main>
    </div>
  );
}
