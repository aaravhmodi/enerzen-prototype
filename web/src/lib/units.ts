// Shared unit-formatting helpers so numbers read with proper typographic
// units (m², kgCO₂e, etc.) everywhere instead of plain-text "m2"/"CO2".

export const M2 = "m²";
export const CO2E = "CO₂e";

export function fmtEui(v: number): string {
  return `${v.toFixed(0)} kWh/${M2}/yr`;
}

export function fmtCarbon(v: number): string {
  return `${v.toFixed(0)} kg${CO2E}/${M2}`;
}

export function fmtArea(v: number): string {
  return `${v.toLocaleString()} ${M2}`;
}

export function fmtCad(v: number): string {
  return `$${Math.round(v).toLocaleString()}`;
}
