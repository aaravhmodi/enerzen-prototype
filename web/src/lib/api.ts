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
  mechanical_option_id: string | null;
  location: string | null;
  num_units: number;
  has_ac: boolean;
  allow_gas: boolean;
  footprint_length_m: number | null;
  footprint_width_m: number | null;
};

export type OptimizationWeights = {
  cost: number;
  speed: number;
  carbon: number;
  energy: number;
};

export type SiteSpecInput = {
  lot_width_m: number;
  lot_depth_m: number;
  street_side: "N" | "S" | "E" | "W";
  front_setback_m: number;
  side_setback_m: number;
  rear_setback_m: number;
  latitude?: number | null;
  longitude?: number | null;
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
  operational_carbon_30yr_kg_co2e_m2: number;
  lifecycle_carbon_30yr_kg_co2e_m2: number;
  eui_kwh_m2_yr: number;
  tedi_kwh_m2_yr: number;
  meui_kwh_m2_yr: number;
  tedi_threshold_kwh_m2_yr: number | null;
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
  soft_cost: number;
  total_project_cost: number;
  [key: string]: unknown;
};

export type SoftTimeline = {
  design_engineering_weeks: number;
  site_plan_weeks: number;
  building_permit_weeks: number;
  total_weeks: number;
  permit_class: string;
  site_plan_exempt: boolean;
};

export type SoftSummary = { soft_cost_fraction: number; timeline: SoftTimeline };

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

export async function fetchCatalog(): Promise<{
  solar: { id: string; name: string }[];
  mechanical: { id: string; name: string; type: string }[];
}> {
  const res = await fetch(`${API_BASE}/catalog`);
  return res.json();
}

export type LocationDetail = {
  municipal_context?: {
    municipality: string;
    retrieved_at: string;
    scope: string;
    layers: { label: string; count: number; source_url: string }[];
    neighbourhoods: string[];
    geometry_note: string;
    sources: { label: string; url: string }[];
  } | null;
  name: string;
  climate_zone: string;
  region_name: string;
  ground_snow_load_kpa: number;
  associated_rain_load_kpa: number;
  roof_snow_load_kpa: number;
  snow_tier: { id: string; name: string; joist_depth_in: number; max_ground_load_kpa: number };
  joist_depth_in: number;
  over_snow_range: boolean;
  allowable_bearing_kpa: number;
  frost_depth_m: number;
  electricity_cad_per_kwh: number;
  natural_gas_cad_per_kwh: number;
  regulatory_intelligence: {
    status: "not_checked" | "not_available";
    label: string;
    detail: string;
    source_url?: string | null;
    source_label?: string | null;
  };
  multifamily_energy_benchmark?: {
    municipality?: string;
    source_url?: string;
    median_kwh_m2_yr: number;
    p25_kwh_m2_yr: number;
    p75_kwh_m2_yr: number;
    reported_rows: number;
    usable_eui_rows: number;
    source_year: number;
    limitation: string;
  } | null;
};

export async function fetchLocationDetail(name: string): Promise<LocationDetail> {
  const res = await fetch(`${API_BASE}/locations/${encodeURIComponent(name)}`);
  if (!res.ok) throw new Error("Failed to fetch location detail");
  return res.json();
}

export type ZoningLookup = {
  status: "available" | "not_found" | "unavailable" | "not_available";
  label: string;
  detail: string;
  parcel?: {
    address?: string | null;
    zoning?: string | null;
    height?: string | null;
    policy_area?: string | null;
    rooming_house?: string | null;
    lot_coverage?: string | null;
    conversion?: string | null;
  };
  source_url?: string;
  source_label?: string;
};

export async function fetchZoningLookup(
  name: string,
  latitude: number,
  longitude: number
): Promise<ZoningLookup> {
  const params = new URLSearchParams({ latitude: String(latitude), longitude: String(longitude) });
  const res = await fetch(`${API_BASE}/locations/${encodeURIComponent(name)}/zoning?${params}`);
  if (!res.ok) throw new Error("Failed to fetch zoning lookup");
  return res.json();
}

export async function runOptimize(
  spec: ProjectSpecInput,
  weights?: OptimizationWeights,
  top_n = 20,
  site?: SiteSpecInput
): Promise<{ results: ConfigResult[]; soft: SoftSummary }> {
  return postJson("/optimize", { spec, weights, top_n, site });
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
  weights?: OptimizationWeights,
  site?: SiteSpecInput,
  top_n_index = 0
): Promise<{ pdf_b64: string }> {
  return postJson("/report", { spec, weights, site, top_n_index });
}

export async function runParseSpec(text: string): Promise<Partial<ProjectSpecInput & SiteSpecInput> & { assumptions: string[] }> {
  return postJson("/parse-spec", { text });
}

export type ArchetypeInfo = {
  id: string;
  name: string;
  floor_area_m2: number;
  storeys: number;
  footprint_length_m: number;
  footprint_width_m: number;
  typology: string;
  units_per_building: number;
};

export type DevSpecInput = {
  lot_width_m: number;
  lot_depth_m: number;
  street_side: "N" | "S" | "E" | "W";
  front_setback_m: number;
  side_setback_m: number;
  rear_setback_m: number;
  total_budget_cad: number;
  location: string;
  target_label: string;
  allowed_types: string[];
  orientation: "N" | "S" | "E" | "W";
  weights: DevelopmentWeights;
};

export type DevelopmentWeights = {
  yield: number;
  cost: number;
  energy: number;
  carbon: number;
};

export type DevMixResult = {
  units: Record<string, number>;
  total_units: number;
  total_cost: number;
  avg_eui_kwh_m2_yr: number;
  avg_carbon_kg_co2e_m2: number;
  nzr_unit_count: number;
  fits_on_lot: boolean;
  total_floor_area_m2: number;
  avg_monthly_utility: number;
  mix_label: string;
  soft_cost: number;
  total_project_cost: number;
  construction_weeks: number;
  soft_timeline_weeks: number;
  lifecycle_carbon_30yr_kg_co2e_m2: number;
  lifecycle_cost_30yr: number;
  configurations: Record<string, string>;
};

// A housing mix that fits the land, before building performance is optimized.
export type DevScenario = {
  units: Record<string, number>;
  dwellings: number;
  screening_cost: number;
  total_floor_area_m2: number;
  site_coverage: number;
  mix_label: string;
};

export type RejectedMix = { units: Record<string, number>; mix_label: string; reason: string };

export async function fetchArchetypes(): Promise<ArchetypeInfo[]> {
  const res = await fetch(`${API_BASE}/archetypes`);
  const data = await res.json();
  return data.archetypes;
}

export async function runDevScenarios(
  spec: DevSpecInput,
  top_n = 10
): Promise<{ scenarios: DevScenario[] }> {
  return postJson("/dev-scenarios", { spec, top_n });
}

export async function runDevOptimize(
  spec: DevSpecInput,
  mixes: Record<string, number>[],
): Promise<{ mixes: DevMixResult[]; rejected: RejectedMix[]; soft_cost_fraction: number }> {
  return postJson("/dev-optimize", { spec, mixes, top_n: mixes.length });
}

export async function runDevSitePlan(
  spec: DevSpecInput,
  mix: Record<string, number>,
  render_concept = false,
): Promise<{ svg: string; concept_render_b64: string | null }> {
  return postJson("/dev-site-plan", { spec, mix, render_concept });
}
