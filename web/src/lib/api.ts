const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export type ProjectSpecInput = {
  typology: string;
  climate_zone: string;
  floor_area_m2: number;
  storeys: number;
  orientation: "N" | "S" | "E" | "W";
  window_to_wall_ratio: number;
  budget_per_unit: number;
  target_label: string;
  solar_option_id: string;
  location: string | null;
  num_units: number;
  has_ac: boolean;
  allow_gas: boolean;
  footprint_length_m: number | null;
  footprint_width_m: number | null;
};

export type SiteSpecInput = {
  lot_width_m: number;
  lot_depth_m: number;
  street_side: "N" | "S" | "E" | "W";
  front_setback_m: number;
  side_setback_m: number;
  rear_setback_m: number;
};

export type ConfigResult = {
  wall_id: string;
  roof_id: string;
  floor_id: string;
  window_id: string;
  mechanical_id: string;
  construction_cost: number;
  construction_weeks: number;
  embodied_carbon_kg_co2e_m2: number;
  eui_kwh_m2_yr: number;
  nzr_compliant: boolean;
  nzr_probability: number;
  energuide_score: number;
  pv_capacity_kw: number;
  pv_generation_kwh_yr: number;
  net_operational_energy_kwh_yr: number;
  net_eui_kwh_m2_yr: number;
  net_zero: boolean;
  annual_utility_cost: number;
  avg_monthly_utility: number;
  lifecycle_cost_30yr: number;
  lifecycle_cost_20yr: number;
  [key: string]: unknown;
};

export type SiteLayout = {
  building_x_m: number;
  building_y_m: number;
  building_w_m: number;
  building_h_m: number;
  driveway_points_m: [number, number][];
  orientation: string;
  solar_score: number;
  fits_on_lot: boolean;
  setbacks_ok: boolean;
  notes: string[];
};

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `${path} failed with ${res.status}`);
  }
  return res.json();
}

export async function fetchLocations(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/locations`);
  const data = await res.json();
  return data.locations;
}

export async function fetchCatalog(): Promise<{ solar: { id: string; name: string }[] }> {
  const res = await fetch(`${API_BASE}/catalog`);
  return res.json();
}

export async function runOptimize(
  spec: ProjectSpecInput,
  weights?: Record<string, number>,
  top_n = 20
): Promise<{ results: ConfigResult[] }> {
  return postJson("/optimize", { spec, weights, top_n });
}

export async function runSitePlan(
  spec: ProjectSpecInput,
  site: SiteSpecInput,
  render_concept = false
): Promise<{ layout: SiteLayout; svg: string; concept_render_b64: string | null }> {
  return postJson("/site-plan", { spec, site, render_concept });
}

export async function runReport(
  spec: ProjectSpecInput,
  top_n_index = 0
): Promise<{ pdf_b64: string }> {
  return postJson("/report", { spec, top_n_index });
}

export async function runParseSpec(text: string): Promise<Partial<ProjectSpecInput & SiteSpecInput> & { assumptions: string[] }> {
  return postJson("/parse-spec", { text });
}
