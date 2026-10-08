"use client";

export type WizardStep = {
  label: string;
  caption: string;
};

export default function WizardChrome({
  steps,
  currentStep,
  eyebrow,
  title,
  description,
  children,
  onBack,
  onNext,
  nextDisabled = false,
  nextLabel = "Continue",
  isLastStep = false,
  submitting = false,
  iteration,
}: {
  steps: WizardStep[];
  currentStep: number;
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
  onBack: () => void;
  onNext: () => void;
  nextDisabled?: boolean;
  nextLabel?: string;
  isLastStep?: boolean;
  submitting?: boolean;
  iteration?: string;
}) {
  return (
    <div className="wizard-shell panel overflow-hidden">
      <div className="relative overflow-hidden border-b border-emerald-100/80 bg-gradient-to-br from-emerald-950 via-emerald-900 to-teal-800 px-5 py-6 text-white sm:px-7">
        <div className="pointer-events-none absolute -right-12 -top-16 h-44 w-44 rounded-full bg-lime-200/15 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 left-1/3 h-44 w-44 rounded-full bg-cyan-300/15 blur-3xl" />
        <div className="relative">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[0.68rem] font-semibold uppercase tracking-[0.2em] text-emerald-200">{eyebrow}</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight">{title}</h2>
              <p className="mt-2 max-w-xl text-sm leading-6 text-emerald-50/75">{description}</p>
            </div>
            {iteration && <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-[10px] font-semibold text-emerald-50">{iteration}</span>}
          </div>

          <ol className="mt-7 grid grid-cols-5 gap-1.5" aria-label="Workflow progress">
            {steps.map((step, index) => {
              const complete = index < currentStep;
              const active = index === currentStep;
              return (
                <li key={step.label} className="min-w-0">
                  <div className={`h-1 rounded-full transition-all duration-500 ${complete || active ? "bg-lime-300" : "bg-white/20"}`} />
                  <div className={`mt-2 truncate text-[10px] font-semibold ${active ? "text-white" : complete ? "text-lime-200" : "text-emerald-100/50"}`} aria-current={active ? "step" : undefined}>
                    {index + 1}. {step.label}
                  </div>
                  <div className="mt-0.5 hidden truncate text-[9px] text-emerald-100/45 sm:block">{step.caption}</div>
                </li>
              );
            })}
          </ol>
        </div>
      </div>

      <div className="animate-screen-in p-5 sm:p-7">{children}</div>

      <div className="flex items-center justify-between gap-3 border-t border-stone-200/80 bg-stone-50/70 px-5 py-4 sm:px-7">
        <button
          type="button"
          onClick={onBack}
          disabled={currentStep === 0 || submitting}
          className="rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-xs font-semibold text-stone-600 transition hover:border-emerald-300 hover:text-emerald-800 disabled:cursor-not-allowed disabled:opacity-35"
        >
          Back
        </button>
        {isLastStep ? (
          <button
            type="submit"
            disabled={nextDisabled || submitting}
            className="rounded-xl bg-emerald-900 px-5 py-2.5 text-xs font-semibold text-white shadow-lg shadow-emerald-900/20 transition hover:-translate-y-0.5 hover:bg-emerald-800 disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting ? "Building scenarios…" : "Generate community plan"}
          </button>
        ) : (
          <button
            type="button"
            onClick={onNext}
            disabled={nextDisabled}
            className="group rounded-xl bg-emerald-900 px-5 py-2.5 text-xs font-semibold text-white shadow-lg shadow-emerald-900/20 transition hover:-translate-y-0.5 hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {nextLabel} <span className="ml-1 transition-transform group-hover:translate-x-0.5">→</span>
          </button>
        )}
      </div>
    </div>
  );
}
