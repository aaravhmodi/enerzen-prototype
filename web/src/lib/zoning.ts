// Pickering zoning: the server's stored copy of the City's data, plus Mapbox for addresses it lacks.
import type { FeatureCollection, Feature } from "geojson";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
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

export type Provision = {
  text: string;
  measures: string[];
  bound: "minimum" | "maximum" | null;
  page: number;
  file: string;
  title: string;
};

export type StoredDoc = { title: string; url: string; file: string; pages?: number | null; kind?: string };

export type Lookup = {
  status: "available" | "not_found" | "not_scraped" | string;
  label: string;
  detail: string;
  retrieved_at?: string;
  matched_property?: { layer: string; field: string; value: unknown };
  steps?: {
    "1_property_identification": {
      from_city_data: {
        address?: string | null;
        roll_number?: string | null;
        pin?: string | null;
        legal_description?: string | null;
        area_m2?: number;
        perimeter_m?: number;
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
  other: "Other City layers",
};
