"use client";

import { useEffect, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import type { Feature, Geometry, Position } from "geojson";
import { CATEGORY_LABELS, MAPBOX_TOKEN, layerLabel, readableFields, type MapData, type MapLayer, type PilotArea } from "@/lib/zoning";

type Props = {
  data: MapData | null;
  hidden: Set<string>;
  onPick: (latitude: number, longitude: number) => void;
  // Called after the map settles at street zoom, to load the layers around the new view.
  onExplore?: (latitude: number, longitude: number) => void;
  workingLot?: { latitude: number; longitude: number; width_m: number; depth_m: number; boundary?: Geometry | null } | null;
  onLotResize?: (width_m: number, depth_m: number, boundary: Geometry) => void;
  // The neighbourhood offered for selection: outlined, its unverified lots greyed out.
  pilot?: PilotArea | null;
};

const PICKERING_CENTER: [number, number] = [-79.09, 43.87];

function kind(layer: MapLayer): "fill" | "line" | "circle" {
  const declared = layer.geometry_type ?? "";
  const first = layer.features.features[0]?.geometry?.type ?? "";
  const type = `${declared} ${first}`;
  if (/Polygon/i.test(type)) return "fill";
  if (/Polyline|LineString/i.test(type)) return "line";
  return "circle";
}

function positions(geometry: Geometry | null | undefined): Position[] {
  if (!geometry) return [];
  switch (geometry.type) {
    case "Point":
      return [geometry.coordinates];
    case "MultiPoint":
    case "LineString":
      return geometry.coordinates;
    case "MultiLineString":
    case "Polygon":
      return geometry.coordinates.flat();
    case "MultiPolygon":
      return geometry.coordinates.flat(2);
    case "GeometryCollection":
      return geometry.geometries.flatMap(positions);
  }
}

function bounds(feature: Feature | null): mapboxgl.LngLatBoundsLike | null {
  const points = positions(feature?.geometry);
  if (!points.length) return null;
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  return [
    [Math.min(...xs), Math.min(...ys)],
    [Math.max(...xs), Math.max(...ys)],
  ];
}

function popupContent(
  hits: mapboxgl.GeoJSONFeature[],
  names: Map<string, string>,
) {
  const root = document.createElement("div");
  root.className = "zoning-popup";
  const seen = new Set<string>();
  for (const hit of hits) {
    const source = String(hit.source);
    const key = `${source}:${hit.id ?? JSON.stringify(hit.properties)}`;
    if (seen.has(key) || !names.has(source)) continue;
    seen.add(key);
    const block = document.createElement("section");
    const title = document.createElement("strong");
    title.textContent = names.get(source) ?? source;
    block.append(title);
    const list = document.createElement("dl");
    for (const [k, v] of readableFields(hit.properties ?? {}).slice(0, 10)) {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = v;
      list.append(dt, dd);
    }
    block.append(list);
    root.append(block);
    if (seen.size >= 4) break;
  }
  return root;
}

function lotRectangle(lot: NonNullable<Props["workingLot"]>): Feature {
  const latMeters = 110_540;
  const lngMeters = 111_320 * Math.cos((lot.latitude * Math.PI) / 180);
  const halfLng = lot.width_m / (2 * lngMeters);
  const halfLat = lot.depth_m / (2 * latMeters);
  return {
    type: "Feature",
    properties: {},
    geometry: {
      type: "Polygon",
      coordinates: [[
        [lot.longitude - halfLng, lot.latitude - halfLat],
        [lot.longitude + halfLng, lot.latitude - halfLat],
        [lot.longitude + halfLng, lot.latitude + halfLat],
        [lot.longitude - halfLng, lot.latitude + halfLat],
        [lot.longitude - halfLng, lot.latitude - halfLat],
      ]],
    },
  };
}

function editableBoundary(lot: NonNullable<Props["workingLot"]>): Geometry {
  return lot.boundary ?? lotRectangle(lot).geometry;
}

function editableCorners(geometry: Geometry): { index: number; coordinate: [number, number] }[] {
  if (geometry.type !== "Polygon" || !geometry.coordinates[0] || geometry.coordinates[0].length < 4) return [];
  const ring = geometry.coordinates[0];
  const open = ring.slice(0, -1);
  const minLng = Math.min(...open.map((point) => point[0]));
  const maxLng = Math.max(...open.map((point) => point[0]));
  const minLat = Math.min(...open.map((point) => point[1]));
  const maxLat = Math.max(...open.map((point) => point[1]));
  const targets: [number, number][] = [[minLng, minLat], [maxLng, minLat], [maxLng, maxLat], [minLng, maxLat]];
  const used = new Set<number>();
  return targets.flatMap(([lng, lat]) => {
    let nearest = -1;
    let distance = Infinity;
    open.forEach((point, index) => {
      if (used.has(index)) return;
      const next = (point[0] - lng) ** 2 + (point[1] - lat) ** 2;
      if (next < distance) { nearest = index; distance = next; }
    });
    if (nearest < 0) return [];
    used.add(nearest);
    return [{ index: nearest, coordinate: [open[nearest][0], open[nearest][1]] as [number, number] }];
  });
}

function moveBoundaryCorner(geometry: Geometry, index: number, coordinate: [number, number]): Geometry {
  if (geometry.type !== "Polygon") return geometry;
  const rings = geometry.coordinates.map((ring) => ring.map((point) => [...point]));
  const ring = rings[0];
  ring[index] = coordinate;
  ring[ring.length - 1] = [...ring[0]];
  return { ...geometry, coordinates: rings };
}

function dimensions(geometry: Geometry, latitude: number): { width: number; depth: number } {
  const points = positions(geometry);
  const lngs = points.map((point) => point[0]);
  const lats = points.map((point) => point[1]);
  return {
    width: (Math.max(...lngs) - Math.min(...lngs)) * 111_320 * Math.cos((latitude * Math.PI) / 180),
    depth: (Math.max(...lats) - Math.min(...lats)) * 110_540,
  };
}

export default function ZoningMap({ data, hidden, onPick, onExplore, workingLot, onLotResize, pilot }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const added = useRef<{ layers: string[]; sources: string[]; byCategory: Map<string, string[]> }>({
    layers: [],
    sources: [],
    byCategory: new Map(),
  });
  const names = useRef(new Map<string, string>());
  const pick = useRef(onPick);
  const explore = useRef(onExplore);
  const resizeLot = useRef(onLotResize);
  const lotMarkers = useRef<mapboxgl.Marker[]>([]);
  const fittedParcel = useRef<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    pick.current = onPick;
    explore.current = onExplore;
    resizeLot.current = onLotResize;
  }, [onPick, onExplore, onLotResize]);

  useEffect(() => {
    if (!MAPBOX_TOKEN || !container.current || map.current) return;
    mapboxgl.accessToken = MAPBOX_TOKEN;
    const instance = new mapboxgl.Map({
      container: container.current,
      style: "mapbox://styles/mapbox/light-v11",
      center: PICKERING_CENTER,
      zoom: 11.5,
    });
    instance.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");
    instance.addControl(new mapboxgl.ScaleControl({ unit: "metric" }), "bottom-left");
    instance.on("load", () => setReady(true));
    // Only moves the person made (not our own fly-to) reload the surrounding layers.
    instance.on("moveend", (event) => {
      if (!("originalEvent" in event) || !event.originalEvent || instance.getZoom() < 15) return;
      const { lat, lng } = instance.getCenter();
      explore.current?.(lat, lng);
    });
    instance.on("click", (event) => {
      const hits = instance.queryRenderedFeatures(event.point);
      pick.current(event.lngLat.lat, event.lngLat.lng);
      if (hits.length) {
        new mapboxgl.Popup({ maxWidth: "320px" })
          .setLngLat(event.lngLat)
          .setDOMContent(popupContent(hits, names.current))
          .addTo(instance);
      }
    });
    map.current = instance;
    // A map built while hidden (a form step not yet shown) measures nothing; redraw when its box changes.
    const resized = new ResizeObserver(() => instance.resize());
    resized.observe(container.current);
    return () => {
      resized.disconnect();
      instance.remove();
      map.current = null;
      setReady(false);
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    const state = added.current;
    for (const id of state.layers) if (instance.getLayer(id)) instance.removeLayer(id);
    for (const id of state.sources) if (instance.getSource(id)) instance.removeSource(id);
    state.layers = [];
    state.sources = [];
    state.byCategory = new Map();
    names.current = new Map();
    const track = (category: string, id: string) => {
      state.layers.push(id);
      state.byCategory.set(category, [...(state.byCategory.get(category) ?? []), id]);
    };

    if (data?.status === "available") data.layers.forEach((layer, i) => {
      const source = `zn-src-${i}`;
      const color = layer.color ?? "#64748b";
      instance.addSource(source, { type: "geojson", data: layer.features });
      state.sources.push(source);
      const category = CATEGORY_LABELS[layer.category] ?? layer.category;
      const label = layerLabel(layer.name);
      names.current.set(source, label.toLowerCase() === category.toLowerCase() ? category : `${category} · ${label}`);
      const shape = kind(layer);
      if (shape === "fill") {
        const base = layer.category === "zoning" || layer.category === "official_plan" ? 0.16 : 0.22;
        instance.addLayer({
          id: `${source}-fill`,
          type: "fill",
          source,
          paint: { "fill-color": color, "fill-opacity": layer.category === "parcels" ? 0.02 : base },
        });
        instance.addLayer({
          id: `${source}-line`,
          type: "line",
          source,
          paint: { "line-color": color, "line-width": layer.category === "parcels" ? 0.6 : 1.2 },
        });
        track(layer.category, `${source}-fill`);
        track(layer.category, `${source}-line`);
        if (layer.category === "zoning") {
          instance.addLayer({
            id: `${source}-label`,
            type: "symbol",
            source,
            layout: { "text-field": ["coalesce", ["get", "_zone"], ""], "text-size": 15 },
            paint: { "text-color": "#302936", "text-halo-color": "#ffffff", "text-halo-width": 1.4 },
          });
          track(layer.category, `${source}-label`);
        }
      } else if (shape === "line") {
        instance.addLayer({
          id: `${source}-line`,
          type: "line",
          source,
          paint: {
            "line-color": color,
            "line-width": layer.category === "rail" ? 3 : 1.6,
            ...(layer.category === "rail" ? { "line-dasharray": [2, 1] } : {}),
          },
        });
        track(layer.category, `${source}-line`);
      } else {
        instance.addLayer({
          id: `${source}-circle`,
          type: "circle",
          source,
          paint: { "circle-color": color, "circle-radius": 3.5, "circle-stroke-color": "#fff", "circle-stroke-width": 1 },
        });
        track(layer.category, `${source}-circle`);
      }
    });

    if (workingLot && workingLot.width_m > 0 && workingLot.depth_m > 0) {
      instance.addSource("zn-working-lot", { type: "geojson", data: { type: "Feature", properties: {}, geometry: editableBoundary(workingLot) } });
      state.sources.push("zn-working-lot");
      instance.addLayer({
        id: "zn-working-lot-fill", type: "fill", source: "zn-working-lot",
        paint: { "fill-color": "#c58a28", "fill-opacity": 0.08 },
      });
      instance.addLayer({
        id: "zn-working-lot-line", type: "line", source: "zn-working-lot",
        paint: { "line-color": "#b87918", "line-width": 3 },
      });
      state.layers.push("zn-working-lot-fill", "zn-working-lot-line");
    }

    if (!data || data.status !== "available") return;

    // Fly to a newly chosen lot; layers reloaded around a panned view leave the camera alone.
    const key = data.parcel ? JSON.stringify(data.parcel.geometry).slice(0, 200) : `${data.center.latitude},${data.center.longitude}`;
    if (data.explored || key === fittedParcel.current) return;
    fittedParcel.current = key;
    const box = bounds(data.parcel);
    if (box) instance.fitBounds(box, { padding: 160, maxZoom: 17.5, duration: 900 });
    else instance.flyTo({ center: [data.center.longitude, data.center.latitude], zoom: 17.5, duration: 900 });
  }, [data, ready, workingLot]);

  // The pilot outline sits under the lot layers and stays put as they reload.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready || !pilot?.boundary) return;
    instance.addSource("zn-pilot", { type: "geojson", data: { type: "Feature", properties: {}, geometry: pilot.boundary } });
    instance.addSource("zn-pilot-unverified", {
      type: "geojson",
      data: pilot.unverified ?? { type: "FeatureCollection", features: [] },
    });
    instance.addLayer({
      id: "zn-pilot-unverified", type: "fill", source: "zn-pilot-unverified",
      paint: { "fill-color": "#78716c", "fill-opacity": 0.45 },
    });
    instance.addLayer({
      id: "zn-pilot-line", type: "line", source: "zn-pilot",
      paint: { "line-color": "#047857", "line-width": 3, "line-dasharray": [3, 1.5] },
    });
    if (pilot.label_point) {
      instance.addSource("zn-pilot-label", { type: "geojson", data: { type: "Feature", properties: {}, geometry: pilot.label_point } });
      instance.addLayer({
        id: "zn-pilot-label", type: "symbol", source: "zn-pilot-label",
        layout: { "text-field": pilot.name, "text-size": 16 },
        paint: { "text-color": "#047857", "text-halo-color": "#ffffff", "text-halo-width": 2 },
      });
    }
    // The base map's own neighbourhood names (e.g. Dunbarton, Liverpool) don't follow the City's boundaries.
    if (instance.getLayer("settlement-subdivision-label")) instance.setLayoutProperty("settlement-subdivision-label", "visibility", "none");
    // Start on the pilot neighbourhood until a lot is chosen.
    if (!fittedParcel.current) {
      const box = bounds({ type: "Feature", properties: {}, geometry: pilot.boundary });
      if (box) instance.fitBounds(box, { padding: 40, duration: 0 });
    }
    return () => {
      // On unmount the map is already removed, and with it these layers.
      if (map.current !== instance) return;
      for (const id of ["zn-pilot-label", "zn-pilot-line", "zn-pilot-unverified"]) if (instance.getLayer(id)) instance.removeLayer(id);
      for (const id of ["zn-pilot", "zn-pilot-label", "zn-pilot-unverified"]) if (instance.getSource(id)) instance.removeSource(id);
    };
  }, [pilot, ready]);

  useEffect(() => {
    const instance = map.current;
    lotMarkers.current.forEach((marker) => marker.remove());
    lotMarkers.current = [];
    if (!instance || !ready || !workingLot || !resizeLot.current) return;
    const boundary = editableBoundary(workingLot);
    const latMeters = 110_540;
    const lngMeters = 111_320 * Math.cos((workingLot.latitude * Math.PI) / 180);
    for (const corner of editableCorners(boundary)) {
      const element = document.createElement("button");
      element.type = "button";
      element.className = "lot-map-handle";
      element.setAttribute("aria-label", "Drag to adjust this lot corner");
      element.title = "Drag to adjust this lot corner";
      element.addEventListener("keydown", (event) => {
        if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
        event.preventDefault();
        const sign = event.key === "ArrowDown" || event.key === "ArrowLeft" ? -1 : 1;
        const next = moveBoundaryCorner(boundary, corner.index, [corner.coordinate[0] + sign * (1 / lngMeters), corner.coordinate[1] + sign * (1 / latMeters)]);
        const size = dimensions(next, workingLot.latitude);
        resizeLot.current?.(Math.max(5, Math.min(500, size.width)), Math.max(5, Math.min(500, size.depth)), next);
      });
      const marker = new mapboxgl.Marker({ element, draggable: true, anchor: "center" })
        .setLngLat(corner.coordinate)
        .addTo(instance);
      marker.on("dragend", () => {
        const point = marker.getLngLat();
        const next = moveBoundaryCorner(boundary, corner.index, [point.lng, point.lat]);
        const size = dimensions(next, workingLot.latitude);
        resizeLot.current?.(Math.max(5, Math.min(500, size.width)), Math.max(5, Math.min(500, size.depth)), next);
      });
      lotMarkers.current.push(marker);
    }
    return () => {
      lotMarkers.current.forEach((marker) => marker.remove());
      lotMarkers.current = [];
    };
  }, [workingLot, ready]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    for (const [category, ids] of added.current.byCategory) {
      for (const id of ids) {
        if (instance.getLayer(id)) instance.setLayoutProperty(id, "visibility", hidden.has(category) ? "none" : "visible");
      }
    }
  }, [hidden, data, ready]);

  if (!MAPBOX_TOKEN) {
    return (
      <div className="zoning-map zoning-map--empty" role="note">
        <p>
          Add <code>NEXT_PUBLIC_MAPBOX_TOKEN</code> to show the map. The lot review beside it works without one.
        </p>
      </div>
    );
  }
  return <div ref={container} className="zoning-map" aria-label="Map of the selected lot and its zoning layers" />;
}
