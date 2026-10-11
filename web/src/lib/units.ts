// Shared unit-formatting helpers so numbers read with proper typographic
// units (m², kgCO₂e, etc.) everywhere instead of plain-text "m2"/"CO2".
// Areas are stored and sent to the API in m² but shown in square feet;
// energy and carbon intensities stay per m², the unit their code targets use.

export const M2 = "m²";
export const SQFT = "sq ft";
export const CO2E = "CO₂e";

const SQFT_PER_M2 = 10.7639;

export function m2ToSqft(m2: number): number {
  return m2 * SQFT_PER_M2;
}

export function sqftToM2(sqft: number): number {
  return sqft / SQFT_PER_M2;
}

export function fmtEui(v: number): string {
  return `${v.toFixed(0)} kWh/${M2}/yr`;
}

export function fmtCarbon(v: number): string {
  return `${v.toFixed(0)} kg${CO2E}/${M2}`;
}

export function fmtArea(m2: number): string {
  return `${Math.round(m2ToSqft(m2)).toLocaleString()} ${SQFT}`;
}

export function fmtCad(v: number): string {
  return `$${Math.round(v).toLocaleString()}`;
}
