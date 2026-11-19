"use client";
import { useQuery } from "@tanstack/react-query";
import { Crosshair, X } from "lucide-react";
import { useState } from "react";
import { venuesApi } from "@/lib/marketplace";
import { cn } from "@/lib/utils";

export interface Place {
  state: string;
  areaIds: string[];
  near: { lat: number; lng: number; radiusKm: number } | null;
}

/** State, then optional areas or "near me" (docs/venues-spec.md 4.11). */
export function PlacePicker({ value, onChange }: { value: Place; onChange: (p: Place) => void }) {
  const { data: states } = useQuery({ queryKey: ["places", "states"], queryFn: venuesApi.states, staleTime: Infinity });
  const { data: areas } = useQuery({
    queryKey: ["places", "areas", value.state], queryFn: () => venuesApi.areas(value.state),
    enabled: !!value.state, staleTime: 3_600_000,
  });
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState("");

  function nearMe() {
    if (!navigator.geolocation) return setGeoError("Location isn't available on this device.");
    setLocating(true);
    setGeoError("");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        onChange({ ...value, areaIds: [], near: { lat: pos.coords.latitude, lng: pos.coords.longitude, radiusKm: 10 } });
      },
      () => { setLocating(false); setGeoError("We couldn't get your location. Pick areas instead."); },
      { enableHighAccuracy: false, timeout: 10_000 },
    );
  }

  const toggle = (id: string) => onChange({
    ...value, near: null,
    areaIds: value.areaIds.includes(id) ? value.areaIds.filter((a) => a !== id) : [...value.areaIds, id],
  });

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <select
          aria-label="State"
          value={value.state}
          onChange={(e) => onChange({ state: e.target.value, areaIds: [], near: null })}
          className="flex-1 h-10 rounded border-2 border-border bg-bg-card px-3 text-sm font-bold text-text"
        >
          {(states ?? [{ id: value.state, label: value.state }]).map((s) => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>
        <button
          type="button" onClick={nearMe}
          className={cn("h-10 px-3 rounded border-2 text-xs font-bold flex items-center gap-1.5",
            value.near ? "bg-primary text-on-primary border-border" : "border-border bg-bg-card text-text")}
        >
          <Crosshair size={14} aria-hidden /> {locating ? "Finding…" : "Near me"}
        </button>
      </div>
      {value.near && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-secondary font-bold">Within</span>
          {[5, 10, 25].map((km) => (
            <button key={km} type="button"
              onClick={() => onChange({ ...value, near: { ...value.near!, radiusKm: km } })}
              className={cn("px-2 py-1 rounded border-2 font-bold",
                value.near!.radiusKm === km ? "bg-primary text-on-primary border-border" : "border-border-subtle text-text-secondary")}>
              {km} km
            </button>
          ))}
          <button type="button" aria-label="Clear near me" onClick={() => onChange({ ...value, near: null })}
            className="ml-auto text-text-muted"><X size={14} /></button>
        </div>
      )}
      {geoError && <p className="text-xs text-error">{geoError}</p>}
      {!value.near && !!areas?.length && (
        <div className="flex gap-1.5 overflow-x-auto pb-1 -mx-4 px-4" role="group" aria-label="Areas">
          {areas.map((a) => (
            <button key={a.id} type="button" onClick={() => toggle(a.id)} aria-pressed={value.areaIds.includes(a.id)}
              className={cn("shrink-0 px-2.5 py-1 rounded-full border-2 text-xs font-bold",
                value.areaIds.includes(a.id) ? "bg-primary text-on-primary border-border" : "border-border-subtle text-text-secondary")}>
              {a.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
