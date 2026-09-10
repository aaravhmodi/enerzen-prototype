"use client";

import { useEffect, useState } from "react";
import { fetchLocationDetail, LocationDetail } from "@/lib/api";
import InfoTooltip from "@/components/InfoTooltip";

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
          <Stat
            label="Climate zone"
            value={`Zone ${detail.climate_zone}`}
            tip="NBCC climate zone (6 / 7a / 7b). Sets the heating/cooling degree-days and the Net Zero Ready energy threshold used in the simulation."
          />
          <Stat
            label="Utility region"
            value={detail.region_name}
            tip="Which electricity/gas delivery territory this location falls in — sets the utility rates used for your monthly bill estimate."
          />

          <Stat
            label="Ground snow load"
            value={`${detail.ground_snow_load_kpa.toFixed(2)} kPa`}
            hint={detail.over_snow_range ? "Exceeds standard options — needs structural review" : detail.snow_tier.name}
            warn={detail.over_snow_range}
            tip="Ss from the NBCC 2015 snow load workbook. Determines which of the two preliminary roof-joist options applies (Option 1 ≤2.5 kPa, Option 2 2.5–3.0 kPa)."
          />
          <Stat
            label="Roof snow load (S)"
            value={`${detail.roof_snow_load_kpa.toFixed(2)} kPa`}
            tip="The actual structural load on the roof, computed from ground snow load per NBCC 2015: S = Is×[Ss×(Cb·Cw·Cs·Ca) + Sr]."
          />
          <Stat
            label="Preliminary joist depth"
            value={`${detail.joist_depth_in}"`}
            tip="Placeholder roof cavity depth selected from the snow tier — deeper joists hold more insulation. Not structural design; an engineer must confirm span/spacing/species."
          />
          <Stat
            label="Associated rain load"
            value={`${detail.associated_rain_load_kpa.toFixed(2)} kPa`}
            tip="Sr — the rain component added to the snow load in the roof structural load formula."
          />

          <Stat
            label="Soil bearing"
            value={`${detail.allowable_bearing_kpa} kPa`}
            tip="Conservative regional default for allowable soil bearing pressure, used to sanity-check foundation sizing. Not a substitute for a site geotechnical report."
          />
          <Stat
            label="Frost depth"
            value={`${detail.frost_depth_m} m`}
            tip="How deep the frost wall / footings must extend below grade in this region. Deeper frost lines mean more foundation concrete and higher cost."
          />

          <Stat
            label="Electricity rate"
            value={`$${detail.electricity_cad_per_kwh.toFixed(3)}/kWh`}
            tip="All-in regional electricity rate used to estimate your monthly utility bill and 30-year lifecycle cost."
          />
          <Stat
            label="Natural gas rate"
            value={`$${detail.natural_gas_cad_per_kwh.toFixed(3)}/kWh`}
            tip="All-in regional natural gas rate, used only if the selected mechanical system burns gas."
          />
        </div>
      )}

      <p className="mt-2 text-[10px] leading-4 text-stone-400">
        Snow load is from the NBCC 2015 workbook. Soil bearing and frost depth are conservative regional
        defaults, not a site investigation — verify with a geotechnical report before final design.
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  warn,
  tip,
}: {
  label: string;
  value: string;
  hint?: string;
  warn?: boolean;
  tip?: string;
}) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-[10px] text-stone-400">
        {label}
        {tip && <InfoTooltip text={tip} />}
      </p>
      <p className={`font-semibold ${warn ? "text-amber-700" : "text-stone-800"}`}>{value}</p>
      {hint && <p className={`text-[10px] ${warn ? "text-amber-600" : "text-stone-400"}`}>{hint}</p>}
    </div>
  );
}
