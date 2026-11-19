"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { apiErrorMessage } from "@/lib/api";
import { portalApi, VENUE_TYPES, venuesApi } from "@/lib/marketplace";
import { useAuthStore } from "@/store/auth";

const STATUS: Record<string, string> = {
  draft: "Draft", in_review: "In review", live: "Live", paused: "Paused", suspended: "Suspended",
};

function CreateVenue() {
  const { token } = useAuthStore();
  const router = useRouter();
  const [name, setName] = useState("");
  const [type, setType] = useState("hall");
  const [state, setState] = useState("Lagos");
  const [areaId, setAreaId] = useState("");
  const [areaOther, setAreaOther] = useState("");
  const [address, setAddress] = useState("");
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [error, setError] = useState("");
  const states = useQuery({ queryKey: ["places", "states"], queryFn: venuesApi.states, staleTime: Infinity });
  const areas = useQuery({ queryKey: ["places", "areas", state], queryFn: () => venuesApi.areas(state) });
  const create = useMutation({
    mutationFn: () => portalApi.create(token!, {
      name, type, state, area_id: areaId && areaId !== "other" ? areaId : null,
      area_other: areaId === "other" ? areaOther : null, address, latitude: Number(lat), longitude: Number(lng),
    }),
    onSuccess: (v) => router.push(`/venue/manage?id=${v.id}`),
    onError: (e) => setError(apiErrorMessage(e, "Couldn't create the venue.")),
  });
  const field = "w-full h-11 rounded border-2 border-border bg-bg-card px-3 text-sm text-text";
  return (
    <form className="space-y-3 max-w-xl" onSubmit={(e) => { e.preventDefault(); setError(""); create.mutate(); }}>
      <Input label="Venue name" required value={name} onChange={(e) => setName(e.target.value)} />
      <label className="block text-xs font-bold uppercase text-text-secondary space-y-1.5">Type
        <select value={type} onChange={(e) => setType(e.target.value)} className={field}>
          {VENUE_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
        </select></label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block text-xs font-bold uppercase text-text-secondary space-y-1.5">State
          <select value={state} onChange={(e) => { setState(e.target.value); setAreaId(""); }} className={field}>
            {states.data?.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select></label>
        <label className="block text-xs font-bold uppercase text-text-secondary space-y-1.5">Area
          <select required value={areaId} onChange={(e) => setAreaId(e.target.value)} className={field}>
            <option value="">Choose…</option>
            {areas.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            <option value="other">Other (type it)</option>
          </select></label>
      </div>
      {areaId === "other" && <Input label="Your area" required value={areaOther} onChange={(e) => setAreaOther(e.target.value)} />}
      <Input label="Street address" required minLength={5} value={address} onChange={(e) => setAddress(e.target.value)} />
      <div className="grid grid-cols-2 gap-3">
        <Input label="Latitude" required inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} />
        <Input label="Longitude" required inputMode="decimal" value={lng} onChange={(e) => setLng(e.target.value)} />
      </div>
      <p className="text-[11px] text-text-muted">Your map pin: open Google Maps, long-press your entrance and copy the two numbers. Or
        <button type="button" className="ml-1 text-primary font-bold underline" onClick={() => navigator.geolocation?.getCurrentPosition(
          (p) => { setLat(p.coords.latitude.toFixed(6)); setLng(p.coords.longitude.toFixed(6)); })}>use where I am now</button>.</p>
      {error && <p className="text-xs text-error">{error}</p>}
      <Button type="submit" loading={create.isPending}>Create listing</Button>
    </form>
  );
}

export default function VenuePortalHome() {
  const { token } = useAuthStore();
  const [creating, setCreating] = useState(false);
  const { data, isPending } = useQuery({ queryKey: ["portal", "mine"], queryFn: () => portalApi.myVenues(token!) });
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-black text-text">Your venues</h1>
        {!creating && <Button size="sm" onClick={() => setCreating(true)}><Plus size={14} aria-hidden /> List a venue</Button>}
      </div>
      {creating && (
        <section className="p-4 rounded border-2 border-primary bg-bg-card space-y-3">
          <h2 className="text-sm font-black uppercase text-text">New listing</h2>
          <p className="text-xs text-text-muted">Next you'll add spaces, photos and payout details, upload verification
            documents (CAC certificate, ID, site photos) and submit. Turnup checks the documents, then the listing goes
            live; deposits open after a Turnup agent visits.</p>
          <CreateVenue />
        </section>
      )}
      {isPending && <div className="h-24 rounded border-2 border-border bg-bg-card animate-pulse" />}
      {data?.length === 0 && !creating && <p className="text-sm text-text-muted">You haven't listed a venue yet.</p>}
      <div className="grid sm:grid-cols-2 gap-3">
        {data?.map((v) => (
          <Link key={v.id} href={`/venue/manage?id=${v.id}`} className="flex gap-3 p-3 rounded border-2 border-border bg-bg-card hover:border-primary">
            <div className="w-16 h-16 rounded bg-bg-elevated overflow-hidden shrink-0">
              {v.cover_image && <img src={v.cover_image} alt="" className="w-full h-full object-cover" />}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-black text-text truncate">{v.name}</p>
              <p className="text-xs text-text-muted">{[v.area, v.state].filter(Boolean).join(", ")}</p>
              <p className="text-[10px] font-black uppercase text-primary">{STATUS[v.status] ?? v.status} · {v.my_role}</p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
