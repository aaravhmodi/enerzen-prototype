"use client";

import { useEffect, useState } from "react";
import { fetchLocationDetail, LocationDetail } from "@/lib/api";

export default function LocationInfoPanel({ location }: { location: string | null | undefined }) {
  const [detail, setDetail] = useState<LocationDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!location) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchLocationDetail(location)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [location]);

  if (!location) return null;

  return (
    <div className="rounded-xl border border-stone-200 bg-stone-50/70 p-3 text-xs">
      <p className="mb-2 flex items-center gap-1.5 font-semibold text-stone-600">
        <span aria-hidden>📍</span> Site data for {location}
      </p>

      {loading && <p className="text-stone-400">Loading…</p>}

      {!loading && detail && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Stat label="Climate zone" value={`Zone ${detail.climate_zone}`} />
          <Stat label="Utility region" value={detail.region_name} />

          <Stat
            label="Ground snow load"
            value={`${detail.ground_snow_load_kpa.toFixed(2)} kPa`}
            hint={detail.over_snow_range ? "Exceeds standard options — needs structural review" : detail.snow_tier.name}
            warn={detail.over_snow_range}
          />
          <Stat label="Roof snow load (S)" value={`${detail.roof_snow_load_kpa.toFixed(2)} kPa`} />
          <Stat label="Preliminary joist depth" value={`${detail.joist_depth_in}"`} />
          <Stat label="Associated rain load" value={`${detail.associated_rain_load_kpa.toFixed(2)} kPa`} />

          <Stat label="Soil bearing" value={`${detail.allowable_bearing_kpa} kPa`} />
          <Stat label="Frost depth" value={`${detail.frost_depth_m} m`} />

          <Stat label="Electricity rate" value={`$${detail.electricity_cad_per_kwh.toFixed(3)}/kWh`} />
          <Stat label="Natural gas rate" value={`$${detail.natural_gas_cad_per_kwh.toFixed(3)}/kWh`} />
        </div>
      )}

      <p className="mt-2 text-[10px] leading-4 text-stone-400">
        Snow load is from the NBCC 2015 workbook. Soil bearing and frost depth are conservative regional
        defaults, not a site investigation — verify with a geotechnical report before final design.
      </p>
    </div>
  );
}

function Stat({ label, value, hint, warn }: { label: string; value: string; hint?: string; warn?: boolean }) {
  return (
    <div>
      <p className="text-[10px] text-stone-400">{label}</p>
      <p className={`font-semibold ${warn ? "text-amber-700" : "text-stone-800"}`}>{value}</p>
      {hint && <p className={`text-[10px] ${warn ? "text-amber-600" : "text-stone-400"}`}>{hint}</p>}
    </div>
  );
}
