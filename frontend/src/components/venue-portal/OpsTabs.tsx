"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, format } from "date-fns";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { EnquiryThread } from "@/components/venues/EnquiryThread";
import { apiErrorMessage } from "@/lib/api";
import {
  BOOKING_STATUS, goToPayment, naira, paymentCallback, portalApi, REFUND_STATUS,
  type Booking, type CancelPreview, type PortalVenue,
} from "@/lib/marketplace";
import { cn } from "@/lib/utils";
import { Card, canManage, fieldCls, isOwner, labelCls, toLocalInput, useVenue } from "./shared";

// ── Enquiries ──────────────────────────────────────────────────────────────────

function QuoteBuilder({ v, enquiryId, defaults, onDone }: {
  v: PortalVenue; enquiryId: string; defaults: { space_id: string | null; starts_at: string; ends_at: string }; onDone: () => void;
}) {
  const { token } = useVenue(v.id);
  const [q, setQ] = useState({
    space_id: defaults.space_id ?? v.spaces[0]?.id ?? "", starts_at: toLocalInput(defaults.starts_at),
    ends_at: toLocalInput(defaults.ends_at), total: "", deposit: "", due: String(v.balance_due_days), inclusions: "", valid_days: "7",
  });
  const [err, setErr] = useState("");
  const set = (k: keyof typeof q) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setQ((x) => ({ ...x, [k]: e.target.value }));
  const send = useMutation({
    mutationFn: () => portalApi.quote(token, v.id, enquiryId, {
      space_id: q.space_id, starts_at: new Date(q.starts_at).toISOString(), ends_at: new Date(q.ends_at).toISOString(),
      total_kobo: Math.round(Number(q.total) * 100), deposit_kobo: q.deposit ? Math.round(Number(q.deposit) * 100) : null,
      balance_due_days: Number(q.due), inclusions: q.inclusions || undefined, valid_days: Number(q.valid_days),
    }),
    onSuccess: onDone, onError: (e) => setErr(apiErrorMessage(e, "Couldn't send the quote.")),
  });
  const total = Number(q.total) || 0;
  const deposit = q.deposit ? Number(q.deposit) : v.deposit_type === "percent" ? total * v.deposit_value / 100 : v.deposit_value / 100;
  return (
    <form className="grid sm:grid-cols-3 gap-2 p-3 rounded border-2 border-primary" onSubmit={(e) => { e.preventDefault(); setErr(""); send.mutate(); }}>
      <label className={labelCls}>Space<select className={fieldCls} value={q.space_id} onChange={set("space_id")}>
        {v.spaces.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <label className={labelCls}>From<input required type="datetime-local" className={fieldCls} value={q.starts_at} onChange={set("starts_at")} /></label>
      <label className={labelCls}>To<input required type="datetime-local" className={fieldCls} value={q.ends_at} onChange={set("ends_at")} /></label>
      <label className={labelCls}>Total (₦)<input required type="number" min={1} className={fieldCls} value={q.total} onChange={set("total")} /></label>
      <label className={labelCls}>Deposit (₦)<input type="number" min={1} className={fieldCls} value={q.deposit} onChange={set("deposit")} placeholder={total ? String(Math.round(deposit)) : "default"} /></label>
      <label className={labelCls}>Balance due (days before)<input type="number" min={0} max={90} className={fieldCls} value={q.due} onChange={set("due")} /></label>
      <label className={`${labelCls} sm:col-span-2`}>What's included<textarea rows={2} className={`${fieldCls} h-auto py-2`} value={q.inclusions} onChange={set("inclusions")} /></label>
      <label className={labelCls}>Valid for (days)<input type="number" min={1} max={60} className={fieldCls} value={q.valid_days} onChange={set("valid_days")} /></label>
      <p className="sm:col-span-3 text-[11px] text-text-muted">Refund policy: {v.refund_policy}. Turnup's commission is taken from each payment; refunds are paid by the venue.</p>
      <div className="sm:col-span-3 flex gap-2"><Button type="submit" size="sm" loading={send.isPending}>Send quote</Button></div>
      {err && <p className="sm:col-span-3 text-xs text-error">{err}</p>}
    </form>
  );
}

export function EnquiriesTab({ v }: { v: PortalVenue }) {
  const { token } = useVenue(v.id);
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [quoting, setQuoting] = useState(false);
  const list = useQuery({ queryKey: ["portal", v.id, "enquiries"], queryFn: () => portalApi.enquiries(token, v.id), refetchInterval: 30_000 });
  const thread = useQuery({ queryKey: ["portal", v.id, "enquiry", open], queryFn: () => portalApi.enquiry(token, v.id, open!), enabled: !!open, refetchInterval: 20_000 });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["portal", v.id, "enquiry", open] }); qc.invalidateQueries({ queryKey: ["portal", v.id, "enquiries"] }); };
  return (
    <div className="grid md:grid-cols-[280px_1fr] gap-4">
      <div className="space-y-2">
        {list.data?.length === 0 && <p className="text-sm text-text-muted">No enquiries yet.</p>}
        {list.data?.map((e) => (
          <button key={e.id} onClick={() => { setOpen(e.id); setQuoting(false); }}
            className={cn("w-full text-left p-2 rounded border-2 bg-bg-card", open === e.id ? "border-primary" : "border-border")}>
            <div className="flex items-center gap-2"><span className="text-sm font-bold text-text truncate flex-1">{e.organizer?.display_name ?? e.organizer?.username}</span>
              {e.unread > 0 && <span className="px-1.5 rounded-full bg-primary text-on-primary text-[10px] font-black">{e.unread}</span>}</div>
            <p className="text-xs text-text-muted">{format(new Date(e.starts_at), "d MMM yyyy")} · {e.guest_count} guests</p>
            <p className="text-[10px] font-black uppercase text-text-secondary">{e.status}{e.organizer_trusted.trusted && " · trusted organizer"}</p>
          </button>
        ))}
      </div>
      <div>
        {thread.data && (
          <div className="space-y-3">
            <Card title={`${thread.data.organizer?.display_name ?? thread.data.organizer?.username} · ${thread.data.guest_count} guests`}
              actions={canManage(v) && !["booked", "closed", "declined"].includes(thread.data.status) && (
                <div className="flex gap-2">
                  <Button size="xs" onClick={() => setQuoting((q) => !q)}>{quoting ? "Close" : "Send quote"}</Button>
                  <Button size="xs" variant="ghost" onClick={async () => {
                    const reason = prompt("Message to the organizer (why you can't host):");
                    if (reason) { await portalApi.decline(token, v.id, thread.data!.id, reason); refresh(); }
                  }}>Decline</Button>
                </div>)}>
              <p className="text-xs text-text-secondary">{format(new Date(thread.data.starts_at), "EEE d MMM yyyy, h:mm a")} – {format(new Date(thread.data.ends_at), "h:mm a")}
                {thread.data.event_type && ` · ${thread.data.event_type}`}{thread.data.budget_kobo ? ` · budget ${naira(thread.data.budget_kobo)}` : ""}
                {` · ${thread.data.organizer_trusted.completed_bookings} completed Turnup bookings`}</p>
            </Card>
            {quoting && <QuoteBuilder v={v} enquiryId={thread.data.id} defaults={{ space_id: thread.data.space?.id ?? null,
              starts_at: thread.data.starts_at, ends_at: thread.data.ends_at }} onDone={() => { setQuoting(false); refresh(); }} />}
            <EnquiryThread enquiry={thread.data} side="venue"
              onSend={canManage(v) ? async (body) => { await portalApi.message(token, v.id, thread.data!.id, body); refresh(); } : undefined} />
          </div>
        )}
        {!open && <p className="text-sm text-text-muted">Pick an enquiry.</p>}
      </div>
    </div>
  );
}

// ── Bookings ───────────────────────────────────────────────────────────────────

function BookingPanel({ v, b, onChange }: { v: PortalVenue; b: Booking; onChange: () => void }) {
  const { token } = useVenue(v.id);
  const [preview, setPreview] = useState<{ kind: "venue" | "unpaid"; p: CancelPreview } | null>(null);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  const [dispute, setDispute] = useState("");
  const live = ["confirmed", "fully_paid"].includes(b.status);
  const overdue = b.status === "confirmed" && b.paid_kobo < b.total_kobo && new Date(b.balance_due_at).getTime() + 86_400_000 < Date.now();
  const run = (fn: () => Promise<unknown>) => fn().then(onChange).catch((e) => setErr(apiErrorMessage(e, "Something went wrong.")));
  return (
    <Card title={`${b.organizer?.display_name ?? b.organizer?.username} · ${BOOKING_STATUS[b.status] ?? b.status}`}>
      <p className="text-sm text-text">{b.space.name} · {format(new Date(b.starts_at), "EEE d MMM yyyy, h:mm a")} – {format(new Date(b.ends_at), "h:mm a")}</p>
      <p className="text-xs text-text-secondary">Total {naira(b.total_kobo)} · paid {naira(b.paid_kobo)} · Turnup commission {naira(b.commission_kobo ?? 0)} ({b.commission_percent}%)
        {b.balance_kobo > 0 && ` · balance due ${format(new Date(b.balance_due_at), "d MMM")}`}</p>
      {b.organizer?.email && <p className="text-xs text-text-secondary">Organizer: {b.organizer.email}{b.organizer.phone ? ` · ${b.organizer.phone}` : ""}</p>}
      {b.refund_requests.map((r) => <p key={r.id} className="text-xs text-text">Refund {naira(r.amount_kobo)}: {REFUND_STATUS[r.status] ?? r.status}</p>)}
      {canManage(v) && live && !preview && (
        <div className="flex flex-wrap gap-2">
          <Button size="xs" variant="ghost" onClick={() => portalApi.cancelBooking(token, v.id, b.id, true).then((p) => setPreview({ kind: "venue", p }))}>Cancel booking</Button>
          {overdue && <Button size="xs" variant="secondary" onClick={() => portalApi.cancelUnpaid(token, v.id, b.id, true).then((p) => setPreview({ kind: "unpaid", p }))}>Cancel: balance unpaid</Button>}
        </div>
      )}
      {preview && (
        <div className="p-3 rounded border-2 border-error/50 space-y-2 text-sm">
          {preview.kind === "venue"
            ? <p>The organizer gets everything back ({naira(preview.p.refund_kobo)}), which you pay in within 72 hours. Turnup keeps its commission, and your venue gets a strike (3 in 12 months suspends the listing).</p>
            : <p>Counts as the organizer cancelling: they get {naira(preview.p.refund_kobo)} back under your policy, which you pay in. No strike.</p>}
          {preview.kind === "venue" && <input className={fieldCls} placeholder="Reason for the organizer" value={reason} onChange={(e) => setReason(e.target.value)} />}
          <div className="flex gap-2">
            <Button size="xs" variant="danger" disabled={preview.kind === "venue" && !reason.trim()}
              onClick={() => run(() => preview.kind === "venue" ? portalApi.cancelBooking(token, v.id, b.id, false, reason) : portalApi.cancelUnpaid(token, v.id, b.id, false)).then(() => setPreview(null))}>Confirm</Button>
            <Button size="xs" variant="ghost" onClick={() => setPreview(null)}>Keep it</Button>
          </div>
        </div>
      )}
      {canManage(v) && (live || b.status === "completed") && (
        <div className="flex gap-2">
          <input className={fieldCls} placeholder="Report a problem (damage, no-show…)" value={dispute} onChange={(e) => setDispute(e.target.value)} />
          <Button size="xs" variant="secondary" disabled={dispute.trim().length < 10}
            onClick={() => run(() => portalApi.dispute(token, v.id, b.id, { reason: "other", description: dispute })).then(() => setDispute(""))}>Open dispute</Button>
        </div>
      )}
      {err && <p className="text-xs text-error">{err}</p>}
    </Card>
  );
}

export function BookingsTab({ v }: { v: PortalVenue }) {
  const { token } = useVenue(v.id);
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["portal", v.id, "bookings"], queryFn: () => portalApi.bookings(token, v.id) });
  if (data?.length === 0) return <p className="text-sm text-text-muted">No bookings yet.</p>;
  return <div className="space-y-3">{data?.map((b) => <BookingPanel key={b.id} v={v} b={b} onChange={() => qc.invalidateQueries({ queryKey: ["portal", v.id, "bookings"] })} />)}</div>;
}

// ── Calendar ───────────────────────────────────────────────────────────────────

export function CalendarTab({ v }: { v: PortalVenue }) {
  const { token } = useVenue(v.id);
  const qc = useQueryClient();
  const start = new Date();
  const end = addDays(start, 120);
  const key = ["portal", v.id, "calendar"];
  const { data } = useQuery({ queryKey: key, queryFn: () => portalApi.calendar(token, v.id, start.toISOString(), end.toISOString()) });
  const [b, setB] = useState({ space_id: "", starts_at: "", ends_at: "", note: "" });
  const [err, setErr] = useState("");
  const items = [
    ...(data?.bookings ?? []).map((x) => ({ id: x.id, kind: "booking" as const, starts_at: x.starts_at, ends_at: x.ends_at,
      space_id: x.space_id, label: `${BOOKING_STATUS[x.status] ?? x.status}: ${x.organizer?.display_name ?? x.organizer?.username ?? ""}` })),
    ...(data?.blocks ?? []).map((x) => ({ id: x.id, kind: "block" as const, starts_at: x.starts_at, ends_at: x.ends_at,
      space_id: x.space_id, label: `Blocked${x.note ? `: ${x.note}` : ""}` })),
  ].sort((a, c) => a.starts_at.localeCompare(c.starts_at));
  const spaceName = (id: string | null) => (id ? v.spaces.find((s) => s.id === id)?.name : "Whole venue");
  return (
    <div className="space-y-4">
      {canManage(v) && (
        <Card title="Block dates">
          <div className="grid sm:grid-cols-4 gap-2">
            <select className={fieldCls} value={b.space_id} onChange={(e) => setB({ ...b, space_id: e.target.value })}>
              <option value="">Whole venue</option>{v.spaces.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
            <input type="datetime-local" className={fieldCls} value={b.starts_at} onChange={(e) => setB({ ...b, starts_at: e.target.value })} aria-label="From" />
            <input type="datetime-local" className={fieldCls} value={b.ends_at} onChange={(e) => setB({ ...b, ends_at: e.target.value })} aria-label="To" />
            <input className={fieldCls} placeholder="Note (private)" value={b.note} onChange={(e) => setB({ ...b, note: e.target.value })} />
          </div>
          <Button size="sm" disabled={!b.starts_at || !b.ends_at} onClick={() => portalApi.addBlock(token, v.id, {
            space_id: b.space_id || null, starts_at: new Date(b.starts_at).toISOString(), ends_at: new Date(b.ends_at).toISOString(), note: b.note || undefined,
          }).then(() => { setB({ space_id: "", starts_at: "", ends_at: "", note: "" }); qc.invalidateQueries({ queryKey: key }); })
            .catch((e) => setErr(apiErrorMessage(e, "Couldn't block those dates.")))}>Block</Button>
          {err && <p className="text-xs text-error">{err}</p>}
        </Card>
      )}
      <Card title="Next 4 months">
        {items.length === 0 && <p className="text-sm text-text-muted">Nothing booked or blocked.</p>}
        {items.map((i) => (
          <div key={i.id} className={cn("flex items-center gap-2 p-2 rounded border-l-4 bg-bg", i.kind === "booking" ? "border-primary" : "border-text-muted")}>
            <div className="flex-1 text-sm"><p className="font-bold text-text">{format(new Date(i.starts_at), "EEE d MMM, h:mm a")} – {format(new Date(i.ends_at), "d MMM, h:mm a")}</p>
              <p className="text-xs text-text-muted">{spaceName(i.space_id)} · {i.label}</p></div>
            {i.kind === "block" && canManage(v) && <Button size="xs" variant="ghost" onClick={() => portalApi.deleteBlock(token, v.id, i.id).then(() => qc.invalidateQueries({ queryKey: key }))}>Remove</Button>}
          </div>
        ))}
      </Card>
    </div>
  );
}

// ── Money: refunds and balance ─────────────────────────────────────────────────

export function MoneyTab({ v }: { v: PortalVenue }) {
  const { token } = useVenue(v.id);
  const qc = useQueryClient();
  const [err, setErr] = useState("");
  const refunds = useQuery({ queryKey: ["portal", v.id, "refunds"], queryFn: () => portalApi.refunds(token, v.id), enabled: canManage(v) });
  const ledger = useQuery({ queryKey: ["portal", v.id, "ledger"], queryFn: () => portalApi.ledger(token, v.id), enabled: canManage(v) });
  if (!canManage(v)) return <p className="text-sm text-text-muted">Only Managers and the Owner can see the venue's money.</p>;
  const back = paymentCallback(`/venue/manage?id=${v.id}&tab=money`);
  const open = refunds.data?.filter((r) => ["awaiting_venue", "overdue", "suspended", "referred"].includes(r.status)) ?? [];
  return (
    <div className="space-y-4">
      <Card title="Refunds you owe">
        <p className="text-[11px] text-text-muted">Refunds are always paid by the venue. Pay each one in within 72 hours; Turnup then sends it to the organizer.
          Late refunds pause your listing (day 3), suspend it with a strike (day 30), and at day 60 the organizer gets your verified business details to claim directly.</p>
        {open.length === 0 && <p className="text-sm text-text-muted">Nothing owed.</p>}
        {open.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center gap-2 p-2 rounded border-2 border-border">
            <div className="flex-1 text-sm"><p className="font-bold text-text">{naira(r.amount_kobo - r.funded_kobo)} · {r.reason.replace(/_/g, " ")}</p>
              <p className="text-xs text-text-muted">{REFUND_STATUS[r.status] ?? r.status} · due {format(new Date(r.due_at), "d MMM, h:mm a")}</p></div>
            <Button size="xs" onClick={() => portalApi.fundRefund(token, v.id, r.id, back).then(goToPayment).catch((e) => setErr(apiErrorMessage(e, "Couldn't start the payment.")))}>Pay refund</Button>
            {isOwner(v) && !r.settled_by_venue && ["overdue", "suspended", "referred"].includes(r.status) && (
              <Button size="xs" variant="ghost" onClick={() => portalApi.settled(token, v.id, r.id).then(() => qc.invalidateQueries({ queryKey: ["portal", v.id, "refunds"] }))}>We paid them directly</Button>)}
          </div>
        ))}
      </Card>
      <Card title={`Balance owed to Turnup: ${naira(ledger.data?.balance_kobo ?? 0)}`} actions={isOwner(v) && (ledger.data?.balance_kobo ?? 0) > 0 && (
        <Button size="xs" onClick={() => portalApi.payLedger(token, v.id, back).then(goToPayment).catch((e) => setErr(apiErrorMessage(e, "Couldn't start the payment.")))}>Pay it off</Button>)}>
        <p className="text-[11px] text-text-muted">Anything owed (late refunds, lost chargebacks) is taken from your next payouts, up to 50% of each (100% while a refund is overdue). Unpaid for 30 days pauses the listing.</p>
        {ledger.data?.entries.map((e) => (
          <div key={e.id} className="flex justify-between text-sm border-b border-border-subtle py-1">
            <span className="text-text-secondary">{format(new Date(e.created_at), "d MMM yyyy")} · {e.kind.replace(/_/g, " ")}{e.note ? ` · ${e.note}` : ""}</span>
            <span className={e.amount_kobo > 0 ? "text-error font-bold" : "text-success font-bold"}>{e.amount_kobo > 0 ? "+" : ""}{naira(e.amount_kobo)}</span>
          </div>
        ))}
      </Card>
      {err && <p className="text-xs text-error">{err}</p>}
    </div>
  );
}
