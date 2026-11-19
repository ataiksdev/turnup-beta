"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { EnquiryThread } from "@/components/venues/EnquiryThread";
import { Card, fieldCls, labelCls } from "@/components/venue-portal/shared";
import { apiErrorMessage } from "@/lib/api";
import { adminMarketApi, naira, REFUND_STATUS } from "@/lib/marketplace";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";

const TABS = ["disputes", "refunds", "reports", "chargebacks", "agents", "areas", "featured", "settings", "access"] as const;
type Tab = (typeof TABS)[number];

function useAct() {
  const qc = useQueryClient();
  const [msg, setMsg] = useState("");
  const act = (fn: () => Promise<unknown>) => { setMsg(""); return fn().then(() => qc.invalidateQueries({ queryKey: ["admin"] })).catch((e) => setMsg(apiErrorMessage(e, "Couldn't do that."))); };
  return { act, msg };
}

function Disputes() {
  const { token } = useAuthStore();
  const { act, msg } = useAct();
  const { data } = useQuery({ queryKey: ["admin", "disputes"], queryFn: () => adminMarketApi.disputes(token!) });
  const [open, setOpen] = useState<string | null>(null);
  const thread = useQuery({ queryKey: ["admin", "dispute-thread", open], queryFn: () => adminMarketApi.disputeThread(token!, open!), enabled: !!open });
  const [form, setForm] = useState({ resolution: "no_refund", amount: "", note: "" });
  return (
    <div className="space-y-3">
      {data?.length === 0 && <p className="text-sm text-text-muted">No open disputes.</p>}
      {data?.map((d) => (
        <Card key={d.id} title={`${d.booking.venue.name} · opened by ${d.side}`}>
          <p className="text-sm text-text">{d.reason.replace(/_/g, " ")}: {d.description}</p>
          <p className="text-xs text-text-muted">Booking {format(new Date(d.booking.starts_at), "d MMM yyyy")} · paid {naira(d.booking.paid_kobo)} · {d.booking.refund_policy}</p>
          {d.evidence.map((u) => <a key={u} href={u} target="_blank" rel="noopener noreferrer" className="text-xs text-primary underline block">{u}</a>)}
          <Button size="xs" variant="secondary" onClick={() => setOpen(open === d.id ? null : d.id)}>{open === d.id ? "Hide messages" : "Read messages"}</Button>
          {open === d.id && thread.data && <div className="max-h-96 overflow-y-auto"><EnquiryThread enquiry={thread.data} side="venue" /></div>}
          <div className="grid sm:grid-cols-3 gap-2">
            <select className={fieldCls} value={form.resolution} onChange={(e) => setForm({ ...form, resolution: e.target.value })}>
              <option value="no_refund">No refund</option><option value="partial">Partial refund</option><option value="full">Full refund</option></select>
            {form.resolution === "partial" && <input className={fieldCls} type="number" placeholder="₦ amount" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />}
            <input className={fieldCls} placeholder="Decision note (sent to both)" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          </div>
          <Button size="sm" disabled={form.note.length < 3} onClick={() => act(() => adminMarketApi.decideDispute(token!, d.id, {
            resolution: form.resolution, refund_kobo: form.amount ? Math.round(Number(form.amount) * 100) : null, note: form.note }))}>Decide</Button>
          <p className="text-[11px] text-text-muted">Any refund is a request the venue must pay in; it's never paid by Turnup.</p>
        </Card>
      ))}
      {msg && <p className="text-xs text-error">{msg}</p>}
    </div>
  );
}

function Refunds() {
  const { token } = useAuthStore();
  const [status, setStatus] = useState("");
  const { data } = useQuery({ queryKey: ["admin", "refunds", status], queryFn: () => adminMarketApi.refunds(token!, status || undefined) });
  return (
    <div className="space-y-2">
      <select className={`${fieldCls} w-auto`} value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">All</option>{Object.keys(REFUND_STATUS).map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</select>
      {data?.map((r) => (
        <div key={r.id} className="flex justify-between gap-2 p-2 rounded border-2 border-border bg-bg-card text-sm">
          <span className="text-text">{r.venue.name} · {naira(r.amount_kobo)} ({naira(r.refunded_kobo)} sent) · {r.reason.replace(/_/g, " ")}</span>
          <span className="text-xs font-bold text-text-secondary">{r.status} · {format(new Date(r.created_at), "d MMM")}</span>
        </div>
      ))}
    </div>
  );
}

function Reports() {
  const { token } = useAuthStore();
  const { act, msg } = useAct();
  const { data } = useQuery({ queryKey: ["admin", "reports"], queryFn: () => adminMarketApi.reports(token!) });
  return (
    <div className="space-y-2">
      {data?.length === 0 && <p className="text-sm text-text-muted">No reports.</p>}
      {data?.map((r) => (
        <Card key={r.id} title={`${r.venue.name} · ${r.status}`}>
          <p className="text-sm text-text">{r.details ?? "(no details)"}</p>
          {r.status === "open" && <div className="flex gap-2">
            <Button size="xs" variant="danger" onClick={() => act(() => adminMarketApi.decideReport(token!, r.id, true))}>Uphold: strike</Button>
            <Button size="xs" variant="ghost" onClick={() => act(() => adminMarketApi.decideReport(token!, r.id, false))}>Dismiss</Button></div>}
        </Card>
      ))}
      {msg && <p className="text-xs text-error">{msg}</p>}
    </div>
  );
}

function Chargebacks() {
  const { token } = useAuthStore();
  const { act } = useAct();
  const { data } = useQuery({ queryKey: ["admin", "chargebacks"], queryFn: () => adminMarketApi.chargebacks(token!) });
  return (
    <div className="space-y-2">
      <p className="text-[11px] text-text-muted">Answer chargebacks in the Paystack dashboard with the booking records. A lost one on a venue payment goes on that venue's balance.</p>
      {data?.map((c) => (
        <div key={c.id} className="flex items-center gap-2 p-2 rounded border-2 border-border bg-bg-card text-sm">
          <span className="flex-1 text-text">{c.reference} · {naira(c.amount_kobo)} · {c.status}</span>
          {c.status === "open" && <><Button size="xs" variant="secondary" onClick={() => act(() => adminMarketApi.decideChargeback(token!, c.id, "won"))}>Won</Button>
            <Button size="xs" variant="danger" onClick={() => act(() => adminMarketApi.decideChargeback(token!, c.id, "lost"))}>Lost</Button></>}
        </div>
      ))}
    </div>
  );
}

function Agents() {
  const { token } = useAuthStore();
  const { act, msg } = useAct();
  const { data } = useQuery({ queryKey: ["admin", "agents"], queryFn: () => adminMarketApi.agents(token!) });
  const [f, setF] = useState({ user_id: "", states: "", phone: "" });
  return (
    <div className="space-y-3">
      {data?.map((a) => (
        <div key={a.user.id} className="flex items-center gap-2 p-2 rounded border-2 border-border bg-bg-card text-sm">
          <span className="flex-1 text-text">{a.user.display_name ?? a.user.username} · {a.states.join(", ")} · {a.open_visits} open, {a.completed_visits} done</span>
          <Button size="xs" variant="ghost" onClick={() => act(() => adminMarketApi.upsertAgent(token!, { user_id: a.user.id, states: a.states, phone: a.phone ?? undefined, is_active: !a.is_active }))}>
            {a.is_active ? "Deactivate" : "Activate"}</Button>
        </div>
      ))}
      <Card title="Add an agent">
        <p className="text-[11px] text-text-muted">The person needs a Turnup account. Get their user ID from Admin → Users. Agent pay is handled outside the app for now.</p>
        <div className="grid sm:grid-cols-3 gap-2">
          <input className={fieldCls} placeholder="User ID" value={f.user_id} onChange={(e) => setF({ ...f, user_id: e.target.value })} />
          <input className={fieldCls} placeholder="States, e.g. Lagos, Ogun" value={f.states} onChange={(e) => setF({ ...f, states: e.target.value })} />
          <input className={fieldCls} placeholder="Phone" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
        </div>
        <Button size="sm" disabled={!f.user_id || !f.states} onClick={() => act(() => adminMarketApi.upsertAgent(token!, {
          user_id: f.user_id.trim(), states: f.states.split(",").map((s) => s.trim()).filter(Boolean), phone: f.phone || undefined, is_active: true }))}>Save agent</Button>
      </Card>
      {msg && <p className="text-xs text-error">{msg}</p>}
    </div>
  );
}

function Areas() {
  const { token } = useAuthStore();
  const { act, msg } = useAct();
  const [state, setState] = useState("FCT");
  const { data } = useQuery({ queryKey: ["admin", "areas", state], queryFn: () => adminMarketApi.areas(token!, state) });
  const [name, setName] = useState("");
  return (
    <div className="space-y-3">
      {!!data?.unmapped.length && (
        <Card title="Venues with a typed area">
          {data.unmapped.map((u) => <p key={u.venue_id} className="text-sm text-text">{u.venue} ({u.state}): "{u.typed}". Add the area here, then map it on the venue's page.</p>)}
        </Card>
      )}
      <div className="flex gap-2">
        <input className={`${fieldCls} w-40`} value={state} onChange={(e) => setState(e.target.value)} aria-label="State" />
        <input className={fieldCls} placeholder="New area name" value={name} onChange={(e) => setName(e.target.value)} />
        <Button size="sm" disabled={name.length < 2} onClick={() => act(() => adminMarketApi.addArea(token!, { state, name, kind: "district" })).then(() => setName(""))}>Add</Button>
      </div>
      <div className="flex flex-wrap gap-2">
        {data?.areas.map((a) => (
          <button key={a.id} onClick={() => act(() => adminMarketApi.editArea(token!, a.id, { is_active: !a.is_active }))}
            className={cn("px-2 py-1 rounded border-2 text-xs font-bold", a.is_active ? "border-border text-text" : "border-border-subtle text-text-muted line-through")}
            title={a.is_active ? "Click to hide" : "Click to show"}>{a.name}</button>
        ))}
      </div>
      {msg && <p className="text-xs text-error">{msg}</p>}
    </div>
  );
}

function Featured() {
  const { token } = useAuthStore();
  const { data } = useQuery({ queryKey: ["admin", "featured"], queryFn: () => adminMarketApi.featuredSlots(token!) });
  return (
    <div className="space-y-2">
      {data?.length === 0 && <p className="text-sm text-text-muted">No featured slots booked.</p>}
      {data?.map((s) => (
        <div key={s.id} className="p-2 rounded border-2 border-border bg-bg-card text-sm text-text">
          w/c {format(new Date(s.week_start), "d MMM yyyy")} · {s.scope === "state" ? `${s.state} (state-wide)` : `${s.area}, ${s.state}`} · {s.venue.name} · {naira(s.amount_kobo)} · {s.status}
        </div>
      ))}
    </div>
  );
}

const SETTING_LABELS: Record<string, [string, "naira" | "number"]> = {
  venue_commission_percent: ["Booking commission %", "number"], featured_state_week_kobo: ["Featured state-wide, per week", "naira"],
  featured_area_week_kobo: ["Featured area, per week", "naira"], featured_max_per_state: ["Featured slots per state", "number"],
  featured_max_per_area: ["Featured slots per area", "number"], max_recovery_percent: ["Max recovery per payment %", "number"],
  refund_funding_hours: ["Hours for the venue to pay a refund", "number"], refund_suspend_days: ["Suspend after (days)", "number"],
  refund_referral_days: ["Refer to the organizer after (days)", "number"], venue_debt_pause_days: ["Pause for unpaid balance after (days)", "number"],
  strike_suspend_count: ["Strikes in 12 months to suspend", "number"], dispute_window_hours: ["Dispute window after the booking (hours)", "number"],
  free_photo_limit: ["Free photos", "number"], pro_photo_limit: ["Pro photos", "number"], free_video_limit: ["Free videos", "number"],
  pro_video_limit: ["Pro videos", "number"], free_team_seats: ["Free team seats", "number"], pro_team_seats: ["Pro team seats", "number"],
  plus_early_alert_hours: ["Turnup+ early alert head start (hours)", "number"], subscription_grace_days: ["Failed-renewal grace (days)", "number"],
};

function Settings() {
  const { token } = useAuthStore();
  const { act, msg } = useAct();
  const { data } = useQuery({ queryKey: ["admin", "market-settings"], queryFn: () => adminMarketApi.settings(token!) });
  const [vals, setVals] = useState<Record<string, string>>({});
  const [plans, setPlans] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!data) return;
    setVals(Object.fromEntries(Object.entries(SETTING_LABELS).map(([k, [, t]]) => [k, String(t === "naira" ? (data[k] as number) / 100 : data[k])])));
    setPlans(Object.fromEntries(data.plans.map((p) => [p.code, String(p.amount_kobo / 100)])));
  }, [data]);
  if (!data) return null;
  return (
    <div className="space-y-4">
      <Card title="Marketplace settings">
        <div className="grid sm:grid-cols-2 gap-2">
          {Object.entries(SETTING_LABELS).map(([k, [label, t]]) => (
            <label key={k} className={labelCls}>{label}{t === "naira" ? " (₦)" : ""}
              <input type="number" className={fieldCls} value={vals[k] ?? ""} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} /></label>
          ))}
        </div>
        <Button size="sm" onClick={() => act(() => adminMarketApi.saveSettings(token!, Object.fromEntries(Object.entries(vals).map(([k, v]) =>
          [k, SETTING_LABELS[k][1] === "naira" ? Math.round(Number(v) * 100) : Number(v)]))))}>Save settings</Button>
      </Card>
      <Card title="Subscription prices">
        <p className="text-[11px] text-text-muted">A new price applies to new subscribers; existing ones keep theirs.</p>
        {data.plans.map((p) => (
          <div key={p.code} className="flex items-center gap-2">
            <span className="flex-1 text-sm text-text">{p.name}</span>
            <input type="number" className={`${fieldCls} w-32`} value={plans[p.code] ?? ""} onChange={(e) => setPlans({ ...plans, [p.code]: e.target.value })} aria-label={`${p.name} price`} />
            <Button size="xs" onClick={() => act(() => adminMarketApi.setPlan(token!, p.code, Math.round(Number(plans[p.code]) * 100), p.is_active))}>Save</Button>
          </div>
        ))}
      </Card>
      {msg && <p className="text-xs text-error">{msg}</p>}
    </div>
  );
}

function Access() {
  const { token } = useAuthStore();
  const { data } = useQuery({ queryKey: ["admin", "access-log"], queryFn: () => adminMarketApi.accessLog(token!) });
  return (
    <div className="space-y-1">
      <p className="text-[11px] text-text-muted">Every view of venue verification files and claim-pack disclosures.</p>
      {data?.map((e, i) => (
        <p key={i} className="text-xs text-text">{format(new Date(e.at), "d MMM yyyy HH:mm")} · {e.user.username} · {e.action} · venue {e.venue_id?.slice(0, 8)} · {e.ip}</p>
      ))}
    </div>
  );
}

const VIEWS: Record<Tab, () => JSX.Element | null> = { disputes: Disputes, refunds: Refunds, reports: Reports, chargebacks: Chargebacks,
  agents: Agents, areas: Areas, featured: Featured, settings: Settings, access: Access };

function Marketplace() {
  const search = useSearchParams();
  const router = useRouter();
  const tab = (TABS.includes(search.get("tab") as Tab) ? search.get("tab") : "disputes") as Tab;
  const View = VIEWS[tab];
  return (
    <div className="pb-24">
      <TopBar title="Marketplace" />
      <div className="p-4 space-y-4">
        <nav className="flex gap-1 overflow-x-auto pb-1" aria-label="Marketplace sections">
          {TABS.map((t) => (
            <button key={t} onClick={() => router.replace(`/admin/marketplace?tab=${t}`)} aria-current={tab === t ? "page" : undefined}
              className={cn("shrink-0 px-2.5 py-1 rounded border-2 text-xs font-bold capitalize", tab === t ? "bg-text text-bg border-border" : "border-border-subtle text-text-secondary")}>
              {t === "access" ? "KYC access log" : t}</button>
          ))}
        </nav>
        <View />
      </div>
    </div>
  );
}

export default function MarketplaceAdminPage() {
  return <Suspense><Marketplace /></Suspense>;
}
