// Pickering zoning: the server's stored copy of the City's data, plus Mapbox for addresses it lacks.
import type { FeatureCollection, Feature } from "geojson";

// The Pickering store lives only on the home server, so a hosted site points this at the server's own API.
export const API_BASE = process.env.NEXT_PUBLIC_ZONING_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
export const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN ?? "";
export const PICKERING_LOCATION = "Pickering (Dunbarton)";
// West, south, east, north: the City of Pickering with a small margin.
export const PICKERING_BBOX: [number, number, number, number] = [-79.23, 43.79, -78.95, 44.04];

export type Candidate = {
  label: string;
  latitude: number;
  longitude: number;
  source: "city" | "mapbox";
  detail?: string;
};

export type MapLayer = {
  category: string;
  name: string;
  source_url: string;
  geometry_type: string | null;
  color: string | null;
  truncated: boolean;
  features: FeatureCollection;
};

export type MapData = {
  status: string;
  center: { latitude: number; longitude: number };
  radius_m: number;
  parcel: Feature | null;
  layers: MapLayer[];
  retrieved_at: string;
  detail?: string;
  // Set when these layers were loaded for a panned view rather than a chosen lot.
  explored?: boolean;
};

export type Hit = {
  layer: string;
  source_url: string;
  distance_m: number;
  parcel_share_pct?: number | null;
  attributes: Record<string, unknown>;
};

export type DocRef = {
  title: string;
  url: string;
  file: string;
  names_parcel_bylaw: string[];
  zone_pages: Record<string, number[]>;
  excerpts: { zone: string; page: number; text: string }[];
};

export type Rule = {
  value: number | null;
  unit?: string | null;
  bound?: string | null;
  from?: string;
  document?: string;
  file?: string;
  page?: number;
  label?: string;
  overrides?: number | null;
  note?: string;
};

export type LotStandards = {
  zone: string | null;
  zone_code: string | null;
  exceptions: string[];
  exceptions_without_text: string[];
  street_side: "N" | "E" | "S" | "W" | null;
  flank_side: "N" | "E" | "S" | "W" | null;
  corner_lot: boolean;
  through_lot: boolean;
  setbacks_by_side: Record<string, Rule & { applies: string }>;
  standards: Record<string, Rule>;
  missing: string[];
  // Standards the zone's table has no column for (the Seaton zones), with what the by-law says instead.
  not_regulated?: Record<string, string>;
  lot_checks: { standard: string; required: number; lot: number; ok: boolean; from: string; page?: number }[];
  buildable_area_m2: number | null;
  max_coverage_m2: number | null;
  complete: boolean;
  approximate: boolean;
  // What the setbacks rest on: yards, a street-line setback, a drawing in the by-law, or nothing stated.
  basis?: "yards" | "street_line" | "figure" | "no_zone" | "no_street" | "partial" | "none_stated";
  basis_note?: string | null;
  basis_page?: number | null;
  basis_document?: string | null;
  // Where the setbacks are drawn: each line's distance as read off the figure, in metres.
  figure_setbacks?: {
    exception: string;
    figure: string;
    document: string;
    page: number;
    applies_to?: string | null;
    note?: string | null;
    setbacks: { from: string; value_m: number; stated: string }[];
  }[];
};

export type Provision = {
  text: string;
  measures: string[];
  bound: "minimum" | "maximum" | null;
  page: number;
  file: string;
  title: string;
};

export type StoredDoc = { title: string; url: string; file: string; pages?: number | null; kind?: string };

type Cite = { document?: string; page?: number | null; file?: string | null; number?: string };
export type AdditionalUnits = {
  zone: string; permitted_in_zone: boolean | null; zone_table: Cite; section: Cite; blockers: string[]; checks: string[];
  max_height_m?: number; min_interior_side_m?: number; min_rear_m?: number; taller_than_m?: number;
  min_side_rear_if_taller_m?: number; max_floor_area_m2?: number; max_share_of_house_pct?: number;
  coverage_pct?: number; footprint_left_m2?: number | null; path_fits?: boolean | null; existing_units?: number;
};

export type DevCharges = {
  kind: string; total: number; retrieved_at: string;
  lines: { authority: string; area?: string; amount: number; services: Record<string, number>; effective?: string | null; url: string }[];
  garden_suite: { municipal: number; basis: string; school_boards: number | null };
};
export type Servicing = { municipal_expected: boolean; in_urban_area: boolean; in_hamlet: boolean; source?: string | null; note: string };

export type PermittedUses = {
  zone: string; dwellings: string[]; other_uses: number; enerzen_units: string[];
  document?: string; file?: string | null; page?: number | null;
};

export type Lookup = {
  permitted_uses?: PermittedUses | null;
  additional_units?: AdditionalUnits | null;
  development_charges?: DevCharges | null;
  servicing?: Servicing | null;
  status: "available" | "not_found" | "not_scraped" | string;
  label: string;
  detail: string;
  retrieved_at?: string;
  matched_property?: { layer: string; field: string; value: unknown };
  query?: { latitude: number; longitude: number };
  buildable_area?: import("geojson").Geometry | null;
  parcel?: Record<string, string>;
  steps?: {
    "1_property_identification": {
      from_city_data: {
        address?: string | null;
        roll_number?: string | null;
        pin?: string | null;
        legal_description?: string | null;
        area_m2?: number;
        perimeter_m?: number;
        dimensions?: {
          width_m: number;
          depth_m: number;
          rotation_deg: number;
          rectangularity: number;
          street_side: "N" | "S" | "E" | "W" | null;
          street_distance_m?: number;
        } | null;
        layer?: string;
        source_url?: string;
        attributes?: Record<string, unknown>;
        note?: string;
      } | null;
      applicant_must_confirm: string[];
    };
    "2_existing_zoning_and_official_plan": {
      zoning: Hit[];
      zone_codes: string[];
      bylaw_numbers: string[];
      official_plan: Hit[];
      overlays: Record<string, Hit[]>;
      neighbourhood: Record<string, unknown>[];
      applicant_must_supply: string[];
    };
    "3_proposed_development": {
      lot_standards: LotStandards;
      applicant_must_supply: string[];
      check_against: string;
      zone_standards_in_bylaw_text: Record<string, Provision[]>;
    };
    "4_site_characteristics": {
      servicing_nearby: Hit[];
      topography: Hit[];
      natural_heritage: Hit[];
      adjacent_zoning: Hit[];
      adjacent_zone_codes: string[];
      applicant_must_supply: string[];
    };
    "5_supporting_documents": {
      always: string[];
      triggered_by_overlays: Record<string, string>;
      by_scale: string[];
      reference: string;
    };
    "6_planning_frameworks": {
      zoning_bylaw_references: DocRef[];
      council_amendments_naming_this_lot: {
        title: string;
        url: string;
        file: string;
        meeting: string | null;
        reasons: string[];
      }[];
      official_plan_designation: (string | null)[];
      provincial: string[];
      all_documents: Record<string, StoredDoc[]>;
    };
  };
};

export type SearchResult = {
  title: string;
  url: string;
  file: string;
  page: number;
  group: string;
  snippet: string;
  hits_on_page: number;
};

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return response.json();
}

// What a looked-up lot gives the design forms: its point, measured sides, street side, and the by-law's
// setbacks. A setback the by-law did not yield is left out, so the form keeps its own value for it.
export type LotForForm = {
  latitude: number;
  longitude: number;
  lot_width_m?: number;
  lot_depth_m?: number;
  street_side?: "N" | "S" | "E" | "W";
  front_setback_m?: number;
  side_setback_m?: number;
  rear_setback_m?: number;
};

export function lotForForm(lookup: Lookup): LotForForm | null {
  if (!lookup.query) return null;
  const lot: LotForForm = { latitude: lookup.query.latitude, longitude: lookup.query.longitude };
  const dims = lookup.steps?.["1_property_identification"].from_city_data?.dimensions;
  if (dims) {
    lot.lot_width_m = dims.width_m;
    lot.lot_depth_m = dims.depth_m;
    if (dims.street_side) lot.street_side = dims.street_side;
  }
  const standards = lookup.steps?.["3_proposed_development"].lot_standards;
  if (standards) {
    const sides = Object.values(standards.setbacks_by_side);
    const pick = (applies: string) => sides.find((v) => v.applies === applies)?.value;
    const front = pick("front_yard");
    const rear = pick("rear_yard");
    // The site planner takes one side setback: the larger of the lot's two.
    const side = Math.max(...sides.filter((v) => v.applies.endsWith("side_yard")).map((v) => v.value ?? 0));
    if (front != null) lot.front_setback_m = front;
    if (rear != null) lot.rear_setback_m = rear;
    if (side > 0) lot.side_setback_m = side;
  }
  return lot;
}

export const docUrl = (file: string, page?: number) =>
  `${API_BASE}/municipal/pickering/documents/file?path=${encodeURIComponent(file)}${page ? `#page=${page}` : ""}`;

export async function searchAddresses(query: string, signal?: AbortSignal): Promise<Candidate[]> {
  const city = await getJson<{ candidates: { label: string; latitude: number; longitude: number; kind: string }[] }>(
    `/municipal/pickering/geocode?q=${encodeURIComponent(query)}`,
    signal,
  ).catch(() => ({ candidates: [] }));
  const found: Candidate[] = city.candidates.map((c) => ({
    label: c.label,
    latitude: c.latitude,
    longitude: c.longitude,
    source: "city",
    detail: c.kind === "parcels" ? "City parcel" : "City address point",
  }));
  if (found.length >= 3 || !MAPBOX_TOKEN || query.trim().length < 3) return found;
  // Mapbox fills in addresses the City's layers do not carry; the lot still comes from City data.
  const params = new URLSearchParams({
    q: query,
    country: "ca",
    bbox: PICKERING_BBOX.join(","),
    proximity: "-79.09,43.84",
    types: "address,street,postcode,place",
    limit: "5",
    access_token: MAPBOX_TOKEN,
  });
  try {
    const response = await fetch(`https://api.mapbox.com/search/geocode/v6/forward?${params}`, { signal });
    if (response.ok) {
      const body = await response.json();
      for (const f of body.features ?? []) {
        const [longitude, latitude] = f.geometry.coordinates;
        found.push({
          label: f.properties.full_address ?? f.properties.name,
          latitude,
          longitude,
          source: "mapbox",
          detail: "Mapbox address",
        });
      }
    }
  } catch {
    // Mapbox is a convenience; the City search above still stands.
  }
  return found;
}

export const lookupPoint = (latitude: number, longitude: number) =>
  getJson<Lookup>(
    `/locations/${encodeURIComponent(PICKERING_LOCATION)}/zoning?latitude=${latitude}&longitude=${longitude}`,
  );

export const mapAround = (latitude: number, longitude: number, radius = 300) =>
  getJson<MapData>(`/municipal/pickering/map?latitude=${latitude}&longitude=${longitude}&radius_m=${radius}`);

export const searchBylaws = (query: string) =>
  getJson<{ total: number; results: SearchResult[] }>(
    `/municipal/pickering/search?q=${encodeURIComponent(query)}&limit=100`,
  );

export type SetbackCoverage = {
  lots: number;
  complete: number;
  corner_lots: number;
  without_zone: number;
  without_street: number;
  by_zone: Record<string, { lots: number; complete: number; missing: Record<string, number> }>;
};

export const setbackCoverage = () => getJson<SetbackCoverage>("/municipal/pickering/setbacks");
export const SETBACKS_CSV = `${API_BASE}/municipal/pickering/setbacks.csv`;

export const dataStatus = () =>
  getJson<{
    status: string;
    retrieved_at?: string;
    layers?: Record<string, { name: string; features: number; source_url: string }[]>;
    documents?: number;
    council_amendments?: number;
    detail?: string;
    completeness?: {
      complete: boolean | null;
      incomplete_layers: { name: string; url: string; features: number; expected: number }[];
      not_downloaded: { name: string; url: string; reason: string }[];
      missing_bylaws: string[];
      pdfs_with_blank_pages: number;
      documents_carried_over?: number;
      errors: number;
    };
  }>("/municipal/pickering/status");

export const CATEGORY_LABELS: Record<string, string> = {
  parcels: "Parcels",
  zoning: "Zoning",
  official_plan: "Official Plan",
  floodplain: "Floodplain & hazards",
  natural_heritage: "Natural heritage",
  heritage: "Cultural heritage",
  easements: "Easements & corridors",
  rail: "Rail",
  provincial_plans: "Provincial plans",
  servicing: "Servicing",
  topography: "Topography",
  addresses: "Address points",
  neighbourhoods: "Neighbourhoods",
  roads: "Roads",
  other: "Other City layers",
};
