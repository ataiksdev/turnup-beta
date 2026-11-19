"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, MapPin, Upload } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";
import { Card, fieldCls, labelCls } from "@/components/venue-portal/shared";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage } from "@/lib/api";
import { agentApi, apiUrl } from "@/lib/marketplace";
import { useAuthStore } from "@/store/auth";

function Visit() {
  const id = useSearchParams().get("id") ?? "";
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["agent", "me"], queryFn: () => agentApi.me(token!), retry: false });
  const { data: v } = useQuery({ queryKey: ["agent", "visit", id], queryFn: () => agentApi.visit(token!, id), enabled: !!id && me.isSuccess });
  const refresh = () => qc.invalidateQueries({ queryKey: ["agent", "visit", id] });
  const [when, setWhen] = useState("");
  const [note, setNote] = useState("");
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [notes, setNotes] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");
  const photo = useRef<HTMLInputElement>(null);
  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key); setMsg("");
    try { await fn(); refresh(); } catch (e) { setMsg(apiErrorMessage(e, "Something went wrong.")); } finally { setBusy(""); }
  };
  if (!v) return <div className="h-40 rounded border-2 border-border bg-bg-card animate-pulse" />;
  const open = ["assigned", "scheduled"].includes(v.status);
  const checkIn = () => {
    setMsg("");
    navigator.geolocation.getCurrentPosition(
      (p) => run("checkin", () => agentApi.checkIn(token!, id, p.coords.latitude, p.coords.longitude, note || undefined)),
      () => setMsg("Allow location access to check in."), { enableHighAccuracy: true, timeout: 15_000 });
  };
  return (
    <div className="space-y-4">
      <Link href="/agent" className="text-xs font-bold text-text-muted">All visits</Link>
      <h1 className="text-2xl font-black text-text">{v.venue.name}</h1>
      <p className="text-sm text-text-secondary">{v.venue.address}, {[v.venue.area, v.venue.state].filter(Boolean).join(", ")}
        {v.venue.latitude != null && <a className="ml-2 text-primary font-bold underline" target="_blank" rel="noopener noreferrer"
          href={`https://www.google.com/maps?q=${v.venue.latitude},${v.venue.longitude}`}><MapPin size={12} className="inline" /> Map</a>}</p>
      <p className="text-xs text-text-muted">Registered: {v.venue.legal_name} · {v.venue.cac_number} · Phone {v.venue.phone ?? "–"}</p>

      <Card title="Listing to check">
        {v.venue.spaces.map((s) => <p key={s.id} className="text-sm text-text">{s.name}: {s.capacity_seated ?? 0} seated, {s.capacity_standing ?? 0} standing</p>)}
        <div className="grid grid-cols-4 gap-2">{v.venue.media.filter((m) => m.kind === "photo").map((m) => <img key={m.url} src={m.url} alt="" className="h-20 w-full object-cover rounded border-2 border-border" />)}</div>
      </Card>

      <Card title="Documents (private; your views are logged)">
        {v.documents.map((d) => (
          <a key={d.id} href={apiUrl(d.url)} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-primary font-bold underline">
            <FileText size={14} /> {d.kind.replace(/_/g, " ")} · {d.original_filename} ({d.status})</a>
        ))}
        <p className="text-[11px] text-text-muted">Links expire after 5 minutes; reload the page for fresh ones.</p>
      </Card>

      {open && (
        <>
          <Card title="1. Schedule">
            <div className="flex gap-2">
              <input type="datetime-local" className={fieldCls} value={when} onChange={(e) => setWhen(e.target.value)} />
              <Button size="sm" disabled={!when} loading={busy === "schedule"} onClick={() => run("schedule", () => agentApi.schedule(token!, id, new Date(when).toISOString()))}>Save</Button>
            </div>
            {v.scheduled_for && <p className="text-xs text-text-muted">Booked for {new Date(v.scheduled_for).toLocaleString()}</p>}
          </Card>
          <Card title="2. Check in at the venue">
            {v.checked_in_at ? <p className="text-sm text-success font-bold">Checked in {new Date(v.checked_in_at).toLocaleString()}, {v.distance_from_venue_m} m from the pin</p> : (
              <>
                <input className={fieldCls} placeholder="If you're more than 300 m from the pin, explain why" value={note} onChange={(e) => setNote(e.target.value)} />
                <Button size="sm" loading={busy === "checkin"} onClick={checkIn}><MapPin size={14} /> Check in here</Button>
              </>
            )}
          </Card>
          <Card title={`3. Photos (${v.photos.length})`}>
            <Button size="sm" variant="secondary" loading={busy === "photo"} onClick={() => photo.current?.click()}><Upload size={14} /> Add photo</Button>
            <input ref={photo} type="file" accept="image/*" capture="environment" hidden
              onChange={(e) => { const f = e.target.files?.[0]; if (f) run("photo", () => agentApi.photo(token!, id, f)); e.target.value = ""; }} />
          </Card>
          <Card title="4. Report">
            {me.data?.checklist.map((c) => (
              <label key={c.id} className="flex items-center gap-2 text-sm text-text">
                <input type="checkbox" checked={!!checks[c.id]} onChange={(e) => setChecks({ ...checks, [c.id]: e.target.checked })} /> {c.label}
              </label>
            ))}
            <label className={labelCls}>Notes<textarea rows={4} className={`${fieldCls} h-auto py-2`} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
            <div className="flex gap-2">
              <Button size="sm" loading={busy === "pass"} disabled={notes.length < 3} onClick={() => run("pass", () => agentApi.report(token!, id, { checklist: checks, notes, outcome: "passed" }))}>Pass: open deposits</Button>
              <Button size="sm" variant="danger" loading={busy === "fail"} disabled={notes.length < 3} onClick={() => run("fail", () => agentApi.report(token!, id, { checklist: checks, notes, outcome: "failed" }))}>Fail</Button>
            </div>
          </Card>
        </>
      )}
      {!open && <Card title={`Outcome: ${v.status}`}><p className="text-sm text-text">{v.notes}</p></Card>}
      {msg && <p className="text-sm text-error">{msg}</p>}
    </div>
  );
}

export default function AgentVisitPage() {
  return <Suspense><Visit /></Suspense>;
}
