"use client";

import { useEffect, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import type { Feature, Geometry, Position } from "geojson";
import { CATEGORY_LABELS, MAPBOX_TOKEN, type MapData, type MapLayer } from "@/lib/zoning";

type Props = {
  data: MapData | null;
  // The area left to build on inside the lot's setbacks, drawn dashed over the lot.
  envelope?: Geometry | null;
  hidden: Set<string>;
  onPick: (latitude: number, longitude: number) => void;
  // Called after the map settles at street zoom, to load the layers around the new view.
  onExplore?: (latitude: number, longitude: number) => void;
  workingLot?: { latitude: number; longitude: number; width_m: number; depth_m: number } | null;
  onLotResize?: (width_m: number, depth_m: number) => void;
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
  lngLat: mapboxgl.LngLat,
  onPick: Props["onPick"],
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
    const entries = Object.entries(hit.properties ?? {}).filter(([k]) => !k.startsWith("_"));
    for (const [k, v] of entries.slice(0, 10)) {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = String(v);
      list.append(dt, dd);
    }
    block.append(list);
    root.append(block);
    if (seen.size >= 4) break;
  }
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Review this lot";
  button.onclick = () => onPick(lngLat.lat, lngLat.lng);
  root.append(button);
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

export default function ZoningMap({ data, envelope, hidden, onPick, onExplore, workingLot, onLotResize }: Props) {
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
      new mapboxgl.Popup({ maxWidth: "320px" })
        .setLngLat(event.lngLat)
        .setDOMContent(popupContent(hits, names.current, event.lngLat, (lat, lng) => pick.current(lat, lng)))
        .addTo(instance);
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
    if (!data || data.status !== "available") return;

    const track = (category: string, id: string) => {
      state.layers.push(id);
      state.byCategory.set(category, [...(state.byCategory.get(category) ?? []), id]);
    };

    data.layers.forEach((layer, i) => {
      const source = `zn-src-${i}`;
      const color = layer.color ?? "#64748b";
      instance.addSource(source, { type: "geojson", data: layer.features });
      state.sources.push(source);
      names.current.set(source, `${CATEGORY_LABELS[layer.category] ?? layer.category} · ${layer.name}`);
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

    if (data.parcel) {
      instance.addSource("zn-parcel", { type: "geojson", data: data.parcel });
      state.sources.push("zn-parcel");
      names.current.set("zn-parcel", "Selected lot");
      instance.addLayer({
        id: "zn-parcel-fill",
        type: "fill",
        source: "zn-parcel",
        paint: { "fill-color": "#4c405b", "fill-opacity": 0.18 },
      });
      instance.addLayer({
        id: "zn-parcel-line",
        type: "line",
        source: "zn-parcel",
        paint: { "line-color": "#211d27", "line-width": 3 },
      });
      state.layers.push("zn-parcel-fill", "zn-parcel-line");
    }
    if (envelope) {
      instance.addSource("zn-envelope", { type: "geojson", data: { type: "Feature", properties: {}, geometry: envelope } });
      state.sources.push("zn-envelope");
      instance.addLayer({
        id: "zn-envelope-line",
        type: "line",
        source: "zn-envelope",
        paint: { "line-color": "#2f6b3a", "line-width": 2, "line-dasharray": [2, 1.5] },
      });
      state.layers.push("zn-envelope-line");
    }

    if (workingLot && workingLot.width_m > 0 && workingLot.depth_m > 0) {
      instance.addSource("zn-working-lot", { type: "geojson", data: lotRectangle(workingLot) });
      state.sources.push("zn-working-lot");
      instance.addLayer({
        id: "zn-working-lot-fill", type: "fill", source: "zn-working-lot",
        paint: { "fill-color": "#c58a28", "fill-opacity": 0.16 },
      });
      instance.addLayer({
        id: "zn-working-lot-line", type: "line", source: "zn-working-lot",
        paint: { "line-color": "#9b6410", "line-width": 3, "line-dasharray": [2, 1] },
      });
      state.layers.push("zn-working-lot-fill", "zn-working-lot-line");
    }

    // Fly to a newly chosen lot; layers reloaded around a panned view leave the camera alone.
    const key = data.parcel ? JSON.stringify(data.parcel.geometry).slice(0, 200) : `${data.center.latitude},${data.center.longitude}`;
    if (data.explored || key === fittedParcel.current) return;
    fittedParcel.current = key;
    const box = bounds(data.parcel);
    if (box) instance.fitBounds(box, { padding: 160, maxZoom: 17.5, duration: 900 });
    else instance.flyTo({ center: [data.center.longitude, data.center.latitude], zoom: 17.5, duration: 900 });
  }, [data, envelope, ready, workingLot]);

  useEffect(() => {
    const instance = map.current;
    lotMarkers.current.forEach((marker) => marker.remove());
    lotMarkers.current = [];
    if (!instance || !ready || !workingLot || !resizeLot.current) return;
    const latMeters = 110_540;
    const lngMeters = 111_320 * Math.cos((workingLot.latitude * Math.PI) / 180);
    const halfLng = workingLot.width_m / (2 * lngMeters);
    const halfLat = workingLot.depth_m / (2 * latMeters);
    const handles = [
      { axis: "width" as const, side: -1, coordinate: [workingLot.longitude - halfLng, workingLot.latitude] as [number, number] },
      { axis: "width" as const, side: 1, coordinate: [workingLot.longitude + halfLng, workingLot.latitude] as [number, number] },
      { axis: "depth" as const, side: -1, coordinate: [workingLot.longitude, workingLot.latitude - halfLat] as [number, number] },
      { axis: "depth" as const, side: 1, coordinate: [workingLot.longitude, workingLot.latitude + halfLat] as [number, number] },
    ];
    for (const handle of handles) {
      const element = document.createElement("button");
      element.type = "button";
      element.className = "lot-map-handle";
      element.setAttribute("aria-label", `Drag to adjust lot ${handle.axis}`);
      element.title = `Drag to adjust lot ${handle.axis}`;
      element.addEventListener("keydown", (event) => {
        if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
        event.preventDefault();
        const increase = event.key === "ArrowUp" || event.key === "ArrowRight";
        const delta = increase ? 1 : -1;
        resizeLot.current?.(
          handle.axis === "width" ? Math.max(5, Math.min(500, workingLot.width_m + delta)) : workingLot.width_m,
          handle.axis === "depth" ? Math.max(5, Math.min(500, workingLot.depth_m + delta)) : workingLot.depth_m,
        );
      });
      const marker = new mapboxgl.Marker({ element, draggable: true, anchor: "center" })
        .setLngLat(handle.coordinate)
        .addTo(instance);
      marker.on("dragend", () => {
        const point = marker.getLngLat();
        const width = handle.axis === "width"
          ? Math.abs(point.lng - workingLot.longitude) * lngMeters * 2
          : workingLot.width_m;
        const depth = handle.axis === "depth"
          ? Math.abs(point.lat - workingLot.latitude) * latMeters * 2
          : workingLot.depth_m;
        resizeLot.current?.(Math.max(5, Math.min(500, width)), Math.max(5, Math.min(500, depth)));
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
