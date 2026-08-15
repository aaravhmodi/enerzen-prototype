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
    <div className="min-h-screen bg-neutral-50">
      <header className="border-b border-neutral-200 bg-white px-6 py-4">
        <h1 className="text-lg font-semibold text-neutral-900">EnerZen Performance Engine</h1>
        <p className="text-sm text-neutral-500">
          Envelope optimization + energy-efficient site placement for Ontario housing
        </p>
      </header>

      <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6 p-6 lg:grid-cols-[380px_1fr]">
        <div>
          <ProjectForm onSubmit={handleSubmit} submitting={submitting} />
        </div>

        <div className="space-y-6">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
          )}

          {!results && !error && (
            <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-neutral-300 text-sm text-neutral-400">
              Fill out the form and click &ldquo;Evaluate project&rdquo; to see results
            </div>
          )}

          {results && (
            <>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-neutral-800">Best-fit configuration</h2>
                <button
                  onClick={handleDownloadReport}
                  disabled={downloadingReport}
                  className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-40"
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
        </div>
      </main>
    </div>
  );
}
