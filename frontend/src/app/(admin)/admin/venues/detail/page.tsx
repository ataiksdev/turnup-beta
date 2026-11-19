"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { FileText } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card, fieldCls } from "@/components/venue-portal/shared";
import { apiErrorMessage } from "@/lib/api";
import { adminMarketApi, apiUrl, naira, REFUND_STATUS, venuesApi } from "@/lib/marketplace";
import { routes } from "@/lib/routes";
import { useAuthStore } from "@/store/auth";

function Detail() {
  const id = useSearchParams().get("id") ?? "";
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const { data: v } = useQuery({ queryKey: ["admin", "venue", id], queryFn: () => adminMarketApi.venue(token!, id), enabled: !!token && !!id });
  const agents = useQuery({ queryKey: ["admin", "agents"], queryFn: () => adminMarketApi.agents(token!), enabled: !!token });
  const areas = useQuery({ queryKey: ["places", "areas", v?.state], queryFn: () => venuesApi.areas(v.state), enabled: !!v?.state });
  const [note, setNote] = useState("");
  const [agentId, setAgentId] = useState("");
  const [adjust, setAdjust] = useState({ amount: "", note: "" });
  const [msg, setMsg] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "venue", id] });
  const act = (fn: () => Promise<unknown>) => { setMsg(""); return fn().then(refresh).catch((e) => setMsg(apiErrorMessage(e, "Couldn't do that."))); };
  if (!v) return <div className="m-4 h-40 rounded border-2 border-border bg-bg-card animate-pulse" />;
  return (
    <div className="pb-24">
      <TopBar title={v.name} back />
      <div className="p-4 space-y-4 max-w-4xl">
        <p className="text-xs font-black uppercase text-primary">{v.status}{v.pause_reason ? ` (${v.pause_reason})` : ""} · {v.verification_status.replace(/_/g, " ")} · deposits {v.deposits_enabled ? "on" : "off"}</p>
        {["live", "paused", "suspended"].includes(v.status) && <Link href={routes.venue(v.slug)} className="text-xs font-bold text-primary underline">Public page</Link>}

        <Card title="Business">
          <p className="text-sm text-text">{v.legal_name} · {v.cac_number} · {v.registered_address}</p>
          <p className="text-sm text-text-secondary">{v.address}, {[v.area ?? v.area_other, v.state].filter(Boolean).join(", ")}</p>
          <p className="text-xs text-text-muted">Owner: {v.owners.map((o: any) => `${o.full_name} (${o.email})`).join(", ")}</p>
          <p className="text-xs text-text">Bank: {v.bank.bank_name} ····{v.bank.account_last4} · {v.bank.account_name}
            {v.bank.name_match === false && <b className="text-warning"> · name doesn't match: check it</b>}</p>
          {!v.area_id && v.area_other && (
            <div className="flex gap-2 items-center">
              <span className="text-xs text-warning font-bold">Typed area "{v.area_other}":</span>
              <select className={`${fieldCls} w-auto h-8`} onChange={(e) => e.target.value && act(() => adminMarketApi.mapArea(token!, id, e.target.value))}>
                <option value="">Map to…</option>{areas.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
              <Link href="/admin/marketplace?tab=areas" className="text-xs text-primary underline">Add area</Link>
            </div>
          )}
        </Card>

        <Card title="Documents">
          {v.documents.map((d: any) => (
            <div key={d.id} className="flex flex-wrap items-center gap-2 text-sm">
              <a href={apiUrl(d.url)} target="_blank" rel="noopener noreferrer" className="flex-1 text-primary font-bold underline flex items-center gap-1">
                <FileText size={14} /> {d.kind.replace(/_/g, " ")} · {d.original_filename}</a>
              <span className="text-[10px] font-black uppercase text-text-secondary">{d.status}</span>
              <Button size="xs" variant="secondary" onClick={() => act(() => adminMarketApi.decideDoc(token!, id, d.id, "approved"))}>Approve</Button>
              <Button size="xs" variant="ghost" onClick={() => { const r = prompt("Why is it rejected?"); if (r) act(() => adminMarketApi.decideDoc(token!, id, d.id, "rejected", r)); }}>Reject</Button>
            </div>
          ))}
          <p className="text-[11px] text-text-muted">Opening a document is logged. Links expire after 5 minutes.</p>
        </Card>

        {v.verification_status === "documents_submitted" && (
          <Card title="Decision: document review">
            <input className={fieldCls} placeholder="Note to the venue (required to reject)" value={note} onChange={(e) => setNote(e.target.value)} />
            <div className="flex gap-2">
              <Button size="sm" onClick={() => act(() => adminMarketApi.verify(token!, id, true, note || undefined))}>Approve: go live</Button>
              <Button size="sm" variant="danger" disabled={!note} onClick={() => act(() => adminMarketApi.verify(token!, id, false, note))}>Send back</Button>
            </div>
            <p className="text-[11px] text-text-muted">Approving makes the listing live and assigns an agent covering {v.state} automatically; deposits open after the visit passes.</p>
          </Card>
        )}

        <Card title="Agent visits">
          {v.visits.map((x: any) => (
            <div key={x.id} className="text-sm text-text border-b border-border-subtle pb-2">
              <p><b>{x.status}</b> · {x.agent.display_name ?? x.agent.username}{x.scheduled_for && ` · ${format(new Date(x.scheduled_for), "d MMM, h:mm a")}`}
                {x.distance_from_venue_m != null && ` · checked in ${x.distance_from_venue_m} m away`}</p>
              {x.distance_note && <p className="text-xs text-text-muted">Distance note: {x.distance_note}</p>}
              {x.notes && <p className="text-xs text-text-secondary">{x.notes} ({x.photos} photos)</p>}
            </div>
          ))}
          <div className="flex gap-2">
            <select className={`${fieldCls} w-auto`} value={agentId} onChange={(e) => setAgentId(e.target.value)}>
              <option value="">Assign agent…</option>
              {agents.data?.filter((a) => a.is_active).map((a) => <option key={a.user.id} value={a.user.id}>{a.user.display_name ?? a.user.username} ({a.states.join(", ")}) · {a.open_visits} open</option>)}
            </select>
            <Button size="sm" disabled={!agentId} onClick={() => act(() => adminMarketApi.assign(token!, id, agentId))}>Assign</Button>
          </div>
        </Card>

        <Card title={`Money · balance owed ${naira(v.balance_kobo)}`}>
          {v.refund_requests.map((r: any) => (
            <p key={r.id} className="text-sm text-text">{naira(r.amount_kobo)} · {r.reason.replace(/_/g, " ")} · {REFUND_STATUS[r.status] ?? r.status}</p>
          ))}
          <div className="flex gap-2">
            <input className={fieldCls} type="number" placeholder="± ₦ (positive = venue owes)" value={adjust.amount} onChange={(e) => setAdjust({ ...adjust, amount: e.target.value })} />
            <input className={fieldCls} placeholder="Reason" value={adjust.note} onChange={(e) => setAdjust({ ...adjust, note: e.target.value })} />
            <Button size="sm" disabled={!adjust.amount || adjust.note.length < 3} onClick={() => act(() => adminMarketApi.adjust(token!, id, Math.round(Number(adjust.amount) * 100), adjust.note))}>Adjust</Button>
          </div>
        </Card>

        <Card title={`Standing · ${v.strikes_last_year} strikes in 12 months`}>
          {v.strikes.map((s: any) => <p key={s.id} className="text-xs text-text-secondary">{format(new Date(s.created_at), "d MMM yyyy")} · {s.reason.replace(/_/g, " ")}{s.note ? `: ${s.note}` : ""}</p>)}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => { const r = prompt("Reason for the strike"); if (r) act(() => adminMarketApi.strike(token!, id, r)); }}>Add strike</Button>
            {v.status === "suspended"
              ? <Button size="sm" onClick={() => act(() => adminMarketApi.suspend(token!, id, false, "Restored by Turnup"))}>Lift suspension</Button>
              : <Button size="sm" variant="danger" onClick={() => { const r = prompt("Reason (sent to the venue)"); if (r) act(() => adminMarketApi.suspend(token!, id, true, r)); }}>Suspend</Button>}
          </div>
        </Card>
        {msg && <p className="text-sm text-error">{msg}</p>}
      </div>
    </div>
  );
}

export default function AdminVenueDetailPage() {
  return <Suspense><Detail /></Suspense>;
}
