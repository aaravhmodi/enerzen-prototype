"use client";

import { createContext, useContext, useEffect, useRef } from "react";
import type { FieldError } from "@/lib/api";

export type WizardStep = { label: string; caption: string };

// The error the form is sending the user back to; fields read it by name.
export const FieldErrorContext = createContext<FieldError | null>(null);

// For a field wrapper: when the current error names this field, mark its
// control invalid, focus it and scroll it into view.
export function useFieldError(name?: string | string[]) {
  const error = useContext(FieldErrorContext);
  const ref = useRef<HTMLLabelElement>(null);
  const active = name && error?.field && [name].flat().includes(error.field) ? error : null;
  useEffect(() => {
    const control = ref.current?.querySelector<HTMLElement>("input, select, textarea, button");
    if (!active || !control) return;
    control.setAttribute("aria-invalid", "true");
    control.focus({ preventScroll: true });
    ref.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    return () => control.removeAttribute("aria-invalid");
  }, [active]);
  return { ref, error: active };
}

export function Field({
  label,
  name,
  children,
}: {
  label: string;
  // API field name(s) this input sets, so errors naming it land here.
  name?: string | string[];
  children: React.ReactNode;
}) {
  const { ref, error } = useFieldError(name);
  return (
    <label ref={ref} className="block text-xs">
      <span className="mb-1.5 block font-medium text-stone-500">{label}</span>
      {children}
      {error && <FieldErrorText error={error} />}
    </label>
  );
}

export function FieldErrorText({ error }: { error: FieldError }) {
  return (
    <span role="alert" className="mt-1.5 block text-xs leading-5 text-red-700">
      {error.message}
      {error.fix && <span className="block font-medium text-stone-700">{error.fix}</span>}
    </span>
  );
}

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
  nextHint,
  nextLabel = "Continue",
  isLastStep = false,
  submitting = false,
  iteration,
  submitLabel = "Generate recommendation",
  facts = [],
  guidance,
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
  // Why Continue is disabled, shown beside it.
  nextHint?: string | null;
  nextLabel?: string;
  isLastStep?: boolean;
  submitting?: boolean;
  iteration?: string;
  submitLabel?: string;
  facts?: { label: string; value: string }[];
  guidance?: string;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    // A field the user was sent back to keeps focus.
    if (document.activeElement?.getAttribute("aria-invalid") === "true") return;
    heading.current?.focus({ preventScroll: true });
  }, [currentStep]);
  function advance() {
    const form = heading.current?.closest("form");
    if (!form?.reportValidity()) return;
    onNext();
  }
  return (
    <div className="wizard-shell">
      <aside className="wizard-rail">
        <p className="micro-label">{eyebrow}</p>
        <h2>
          Make it
          <br />
          your own.
        </h2>
        <ol aria-label="Workflow progress">
          {steps.map((step, index) => (
            <li
              key={step.label}
              className={
                index === currentStep
                  ? "active"
                  : index < currentStep
                    ? "complete"
                    : ""
              }
              aria-current={index === currentStep ? "step" : undefined}
            >
              <span className="step-number">
                {index < currentStep ? "✓" : String(index + 1).padStart(2, "0")}
              </span>
              <span>
                <strong>{step.label}</strong>
                <small>{step.caption}</small>
              </span>
            </li>
          ))}
        </ol>
        <div className="live-brief" aria-label="Live project brief">
          <p className="micro-label">Taking shape</p>
          <dl>
            {facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd key={fact.value} className="value-arrive">
                  {fact.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="rail-note">
          <span className="status-dot" />
          <p>
            Your choices.
            <br />
            One connected picture.
          </p>
        </div>
      </aside>
      <section className="wizard-stage" aria-busy={submitting}>
        <div className="wizard-stage-top">
          <span className="micro-label">
            Step {String(currentStep + 1).padStart(2, "0")}{" "}
            <span className="muted">
              / {String(steps.length).padStart(2, "0")}
            </span>
          </span>
          {iteration && <span className="micro-label">{iteration}</span>}
        </div>
        <div className="wizard-progress" aria-hidden="true">
          <span
            style={{ width: `${((currentStep + 1) / steps.length) * 100}%` }}
          />
        </div>
        <div key={currentStep} className="wizard-content animate-screen-in">
          <header className="step-heading">
            <h2 ref={heading} tabIndex={-1} aria-label={title}>
              {title.split(" ").map((word, index) => (
                <span
                  aria-hidden="true"
                  className="word-reveal"
                  key={index}
                  style={{ animationDelay: `${index * 65}ms` }}
                >
                  {word}{" "}
                </span>
              ))}
            </h2>
            <p className="description-reveal">{description}</p>
          </header>
          <fieldset disabled={submitting} className="wizard-fields">
            {children}
          </fieldset>
          {guidance && (
            <aside
              className="choice-guidance"
              aria-live="polite"
              aria-atomic="true"
            >
              <span className="guidance-icon" aria-hidden="true">
                ↳
              </span>
              <div key={guidance} className="value-arrive">
                <span className="micro-label">A thought for your project</span>
                <p>{guidance}</p>
              </div>
            </aside>
          )}
        </div>
        <div className="wizard-actions">
          <button
            type="button"
            className="quiet-button"
            onClick={onBack}
            disabled={currentStep === 0 || submitting}
          >
            ← Back
          </button>
          <span className="wizard-action-note" role="status">
            {nextDisabled && nextHint ? nextHint : "Your choices stay as you go."}
          </span>
          {isLastStep ? (
            <button
              key="submit"
              type="submit"
              className="primary-button"
              disabled={nextDisabled || submitting}
            >
              {submitting ? "Exploring…" : submitLabel}{" "}
              <span aria-hidden="true">↗</span>
            </button>
          ) : (
            <button
              key="advance"
              type="button"
              className="primary-button"
              onClick={(event) => {
                event.preventDefault();
                advance();
              }}
              disabled={nextDisabled || submitting}
            >
              {nextLabel} <span aria-hidden="true">→</span>
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
