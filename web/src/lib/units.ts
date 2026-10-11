// Shared unit-formatting helpers so numbers read with proper typographic
// units (m², kgCO₂e, etc.) everywhere instead of plain-text "m2"/"CO2".
//
// Form state and the API are always SI. The unit system is a display choice:
// `useUnits()` returns formatters for the system picked in the header, and
// converts form inputs to and from SI.

import { useSyncExternalStore } from "react";

export type UnitSystem = "imperial" | "metric";

export const CO2E = "CO₂e";

const DEFAULT_SYSTEM: UnitSystem = "imperial";
const STORAGE_KEY = "enerzen-units";

const SQFT_PER_M2 = 10.7639;
const FT_PER_M = 3.28084;
const PSF_PER_KPA = 20.8854;

export interface Units {
  system: UnitSystem;
  imperial: boolean;
  lengthUnit: string;
  areaUnit: string;
  /** "1,615 sq ft" / "150 m²" */
  area(m2: number): string;
  /** "98.4 ft" / "30 m" */
  length(m: number): string;
  /** Several lengths sharing one unit: "98.4 × 164 ft" / "30 × 50 m" */
  dims(...m: number[]): string;
  /** Per-area intensity as a bare number; `digits` is the metric precision. */
  intensity(perM2: number, digits?: number): string;
  /** "5.6 kWh/sq ft/yr" / "60 kWh/m²/yr" */
  eui(kwhPerM2Yr: number): string;
  /** "23.2 kgCO₂e/sq ft" / "250 kgCO₂e/m²" */
  carbon(kgPerM2: number): string;
  /** "23 psf" / "1.10 kPa"; `digits` is the metric precision. */
  pressure(kpa: number, digits?: number): string;
  /** Form inputs: SI state shown in, and read back from, the display unit. */
  lengthInput(m: number): number;
  lengthFromInput(value: number): number;
  areaInput(m2: number): number;
  areaFromInput(value: number): number;
  /** A metric `step` only fits metric values; imperial inputs take any value. */
  lengthStep(metricStep: number): number | "any";
}

function trim(value: number, digits: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function build(system: UnitSystem): Units {
  const imperial = system === "imperial";
  const lengthUnit = imperial ? "ft" : "m";
  const areaUnit = imperial ? "sq ft" : "m²";
  const lengthNumber = (m: number) => (imperial ? trim(m * FT_PER_M, 1) : trim(m, 2));
  // An extra decimal in imperial keeps the same resolution after dividing by ~10.8.
  const intensity = (perM2: number, digits = 0) =>
    imperial ? (perM2 / SQFT_PER_M2).toFixed(digits + 1) : perM2.toFixed(digits);
  return {
    system,
    imperial,
    lengthUnit,
    areaUnit,
    area: (m2) => `${imperial ? trim(m2 * SQFT_PER_M2, 0) : trim(m2, 1)} ${areaUnit}`,
    length: (m) => `${lengthNumber(m)} ${lengthUnit}`,
    dims: (...m) => `${m.map(lengthNumber).join(" × ")} ${lengthUnit}`,
    intensity,
    eui: (v) => `${intensity(v)} kWh/${areaUnit}/yr`,
    carbon: (v) => `${intensity(v)} kg${CO2E}/${areaUnit}`,
    pressure: (kpa, digits = 2) => (imperial ? `${trim(kpa * PSF_PER_KPA, 0)} psf` : `${kpa.toFixed(digits)} kPa`),
    lengthInput: (m) => (imperial ? Math.round(m * FT_PER_M * 100) / 100 : m),
    lengthFromInput: (value) => (imperial ? value / FT_PER_M : value),
    areaInput: (m2) => (imperial ? Math.round(m2 * SQFT_PER_M2) : m2),
    areaFromInput: (value) => (imperial ? value / SQFT_PER_M2 : value),
    lengthStep: (metricStep) => (imperial ? "any" : metricStep),
  };
}

const UNITS: Record<UnitSystem, Units> = { imperial: build("imperial"), metric: build("metric") };

// The choice lives outside React so every component reads the same value and
// it survives a reload.
let current: UnitSystem | null = null;
const listeners = new Set<() => void>();

function read(): UnitSystem {
  if (current === null) {
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem(STORAGE_KEY);
    } catch {
      // Storage can be blocked; fall back to the default.
    }
    current = saved === "metric" || saved === "imperial" ? saved : DEFAULT_SYSTEM;
  }
  return current;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function setUnitSystem(system: UnitSystem) {
  current = system;
  try {
    window.localStorage.setItem(STORAGE_KEY, system);
  } catch {
    // Not persisted; the choice still holds for this visit.
  }
  listeners.forEach((listener) => listener());
}

export function useUnits(): Units {
  return UNITS[useSyncExternalStore(subscribe, read, () => DEFAULT_SYSTEM)];
}

export function fmtCad(v: number): string {
  return `$${Math.round(v).toLocaleString()}`;
}
