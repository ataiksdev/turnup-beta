"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Circle, GripVertical, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage, uploadImage } from "@/lib/api";
import { naira, portalApi, VENUE_TYPES, type PortalVenue, type Space } from "@/lib/marketplace";
import { Card, canManage, fieldCls, isOwner, labelCls, useVenue } from "./shared";

// ── Overview ───────────────────────────────────────────────────────────────────

export function OverviewTab({ v }: { v: PortalVenue }) {
  const { token, setVenue } = useVenue(v.id);
  const [error, setError] = useState("");
  const submit = useMutation({
    mutationFn: () => portalApi.submit(token, v.id), onSuccess: setVenue,
    onError: (e) => setError(apiErrorMessage(e, "Couldn't submit.")),
  });
  const steps = [
    ["Submit for review", v.verification_status !== "none" && v.verification_status !== "rejected"],
    ["Documents approved: listing live", ["documents_approved", "visit_passed"].includes(v.verification_status)],
    ["Turnup visit passed: deposits open", v.verification_status === "visit_passed"],
  ] as const;
  return (
    <div className="space-y-4">
      {v.status === "paused" && <p className="p-3 rounded border-2 border-warning bg-warning/10 text-sm text-text">
        Your listing is paused {v.pause_reason === "unpaid_refund" ? "because a refund is overdue" : v.pause_reason === "debt" ? "because your Turnup balance is unpaid" : ""}. See Money.</p>}
      {v.status === "suspended" && <p className="p-3 rounded border-2 border-error bg-error/10 text-sm text-text">
        Your listing is suspended{v.pause_reason === "strikes" ? " after 3 strikes in 12 months" : v.pause_reason === "unpaid_refund" ? " because a refund is still unpaid" : ""}. Contact Turnup support.</p>}
      {v.verification_note && <p className="p-3 rounded border-2 border-border text-sm text-text">Turnup: {v.verification_note}</p>}
      <Card title="Getting verified">
        <ol className="space-y-2">
          {steps.map(([label, done]) => (
            <li key={label} className="flex items-center gap-2 text-sm text-text">
              {done ? <CheckCircle2 size={16} className="text-success" /> : <Circle size={16} className="text-text-muted" />} {label}
            </li>
          ))}
        </ol>
        {v.visit && <p className="text-xs text-text-muted">Agent visit: {v.visit.status}{v.visit.scheduled_for ? `, ${new Date(v.visit.scheduled_for).toLocaleString()}` : ""}</p>}
      </Card>
      {["draft", "in_review"].includes(v.status) && v.verification_status !== "documents_submitted" && (
        <Card title="Before you submit">
          <ul className="space-y-1.5">
            {v.checklist.map((c) => (
              <li key={c.id} className="flex items-center gap-2 text-sm text-text">
                {c.done ? <CheckCircle2 size={15} className="text-success" /> : <Circle size={15} className="text-text-muted" />} {c.label}
              </li>
            ))}
          </ul>
          {isOwner(v) && <Button loading={submit.isPending} disabled={!v.checklist.every((c) => c.done)} onClick={() => submit.mutate()}>Submit for review</Button>}
          {error && <p className="text-xs text-error">{error}</p>}
        </Card>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {[["Followers", v.followers_count], ["Balance owed", naira(v.balance_kobo)], ["Late refunds", v.late_refunds],
          ["Strikes (12 mo)", v.strikes_last_year]].map(([l, n]) => (
          <div key={l} className="p-3 rounded border-2 border-border bg-bg-card">
            <p className="text-[10px] font-black uppercase text-text-muted">{l}</p><p className="text-lg font-black text-text">{n}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Listing ────────────────────────────────────────────────────────────────────

export function ListingTab({ v }: { v: PortalVenue }) {
  const { token, setVenue, refresh } = useVenue(v.id);
  const [form, setForm] = useState({
    name: v.name, type: v.type, description: v.description ?? "", address: v.address, phone: v.phone ?? "",
    email: v.email ?? "", rules: v.rules ?? "", amenities: v.amenities.join(", "), price_display: v.price_display,
    refund_preset: v.refund_preset, deposit_type: v.deposit_type,
    deposit_value: v.deposit_type === "fixed" ? String(v.deposit_value / 100) : String(v.deposit_value),
    balance_due_days: String(v.balance_due_days),
  });
  const [msg, setMsg] = useState("");
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));
  const save = useMutation({
    mutationFn: () => portalApi.update(token, v.id, {
      ...form, amenities: form.amenities.split(",").map((a) => a.trim()).filter(Boolean),
      deposit_value: form.deposit_type === "fixed" ? Math.round(Number(form.deposit_value) * 100) : Number(form.deposit_value),
      balance_due_days: Number(form.balance_due_days), phone: form.phone || null, email: form.email || null,
    }),
    onSuccess: (r) => { setVenue(r); setMsg("Saved"); }, onError: (e) => setMsg(apiErrorMessage(e, "Couldn't save.")),
  });
  const editable = canManage(v);
  return (
    <div className="space-y-4">
      <Card title="Details">
        <fieldset disabled={!editable} className="grid sm:grid-cols-2 gap-3">
          <label className={labelCls}>Name<input className={fieldCls} value={form.name} onChange={set("name")} /></label>
          <label className={labelCls}>Type<select className={fieldCls} value={form.type} onChange={set("type")}>
            {VENUE_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select></label>
          <label className={`${labelCls} sm:col-span-2`}>Description<textarea rows={4} className={`${fieldCls} h-auto py-2`} value={form.description} onChange={set("description")} /></label>
          <label className={`${labelCls} sm:col-span-2`}>Address<input className={fieldCls} value={form.address} onChange={set("address")} /></label>
          <label className={labelCls}>Phone (shared after booking)<input className={fieldCls} value={form.phone} onChange={set("phone")} /></label>
          <label className={labelCls}>Email (shared after booking)<input className={fieldCls} value={form.email} onChange={set("email")} /></label>
          <label className={`${labelCls} sm:col-span-2`}>Amenities (comma separated)<input className={fieldCls} value={form.amenities} onChange={set("amenities")} placeholder="Parking, Generator, AC, Stage, Bar" /></label>
          <label className={`${labelCls} sm:col-span-2`}>House rules<textarea rows={3} className={`${fieldCls} h-auto py-2`} value={form.rules} onChange={set("rules")} /></label>
        </fieldset>
      </Card>
      <Card title="Prices and policies">
        <fieldset disabled={!editable} className="grid sm:grid-cols-2 gap-3">
          <label className={labelCls}>Show prices<select className={fieldCls} value={form.price_display} onChange={set("price_display")}>
            <option value="from">"From" price</option><option value="range">Price range</option><option value="on_request">Price on request</option></select></label>
          <label className={labelCls}>Refund policy<select className={fieldCls} value={form.refund_preset} onChange={set("refund_preset")}>
            <option value="flexible">Flexible</option><option value="moderate">Moderate</option><option value="strict">Strict</option></select></label>
          <label className={labelCls}>Deposit<select className={fieldCls} value={form.deposit_type} onChange={set("deposit_type")}>
            <option value="percent">% of the quote</option><option value="fixed">Fixed amount (₦)</option></select></label>
          <label className={labelCls}>{form.deposit_type === "percent" ? "Deposit %" : "Deposit ₦"}<input type="number" className={fieldCls} value={form.deposit_value} onChange={set("deposit_value")} /></label>
          <label className={labelCls}>Balance due (days before)<input type="number" min={0} max={90} className={fieldCls} value={form.balance_due_days} onChange={set("balance_due_days")} /></label>
        </fieldset>
        <p className="text-[11px] text-text-muted">{v.refund_policy}. Refunds are always paid by the venue. Turnup's commission is taken from every payment.</p>
      </Card>
      {editable && <div className="flex items-center gap-3"><Button loading={save.isPending} onClick={() => save.mutate()}>Save listing</Button><span className="text-xs text-text-muted">{msg}</span></div>}
      <SpacesCard v={v} onChange={refresh} />
      <MediaCard v={v} />
    </div>
  );
}

function SpaceForm({ initial, onSave, onCancel }: { initial?: Space; onSave: (s: Partial<Space>) => Promise<unknown>; onCancel?: () => void }) {
  const [s, setS] = useState({
    name: initial?.name ?? "", description: initial?.description ?? "", capacity_seated: String(initial?.capacity_seated ?? ""),
    capacity_standing: String(initial?.capacity_standing ?? ""), setting: initial?.setting ?? "indoor",
    price_from: initial?.price_from_kobo ? String(initial.price_from_kobo / 100) : "",
    price_to: initial?.price_to_kobo ? String(initial.price_to_kobo / 100) : "", price_unit: initial?.price_unit ?? "per_day",
  });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof s) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setS((x) => ({ ...x, [k]: e.target.value }));
  const num = (x: string) => (x.trim() ? Number(x) : null);
  return (
    <form className="grid sm:grid-cols-3 gap-2 p-3 rounded border-2 border-dashed border-border" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setErr("");
      try {
        await onSave({ name: s.name, description: s.description || null, capacity_seated: num(s.capacity_seated),
          capacity_standing: num(s.capacity_standing), setting: s.setting,
          price_from_kobo: s.price_from ? Math.round(Number(s.price_from) * 100) : null,
          price_to_kobo: s.price_to ? Math.round(Number(s.price_to) * 100) : null, price_unit: s.price_unit as Space["price_unit"] });
      } catch (x) { setErr(apiErrorMessage(x, "Couldn't save the space.")); } finally { setBusy(false); }
    }}>
      <label className={labelCls}>Space name<input required className={fieldCls} value={s.name} onChange={set("name")} placeholder="Main hall" /></label>
      <label className={labelCls}>Seated<input type="number" className={fieldCls} value={s.capacity_seated} onChange={set("capacity_seated")} /></label>
      <label className={labelCls}>Standing<input type="number" className={fieldCls} value={s.capacity_standing} onChange={set("capacity_standing")} /></label>
      <label className={labelCls}>Price from (₦)<input type="number" className={fieldCls} value={s.price_from} onChange={set("price_from")} /></label>
      <label className={labelCls}>Price to (₦)<input type="number" className={fieldCls} value={s.price_to} onChange={set("price_to")} /></label>
      <label className={labelCls}>Per<select className={fieldCls} value={s.price_unit} onChange={set("price_unit")}>
        <option value="per_day">Day</option><option value="per_hour">Hour</option><option value="per_event">Event</option></select></label>
      <label className={labelCls}>Setting<select className={fieldCls} value={s.setting} onChange={set("setting")}>
        <option value="indoor">Indoor</option><option value="outdoor">Outdoor</option><option value="both">Both</option></select></label>
      <label className={`${labelCls} sm:col-span-2`}>Description<input className={fieldCls} value={s.description} onChange={set("description")} /></label>
      <div className="sm:col-span-3 flex gap-2"><Button type="submit" size="sm" loading={busy}>Save space</Button>
        {onCancel && <Button type="button" size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>}</div>
      {err && <p className="sm:col-span-3 text-xs text-error">{err}</p>}
    </form>
  );
}

function SpacesCard({ v, onChange }: { v: PortalVenue; onChange: () => void }) {
  const { token } = useVenue(v.id);
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(v.spaces.length === 0);
  return (
    <Card title="Spaces" actions={canManage(v) && !adding && <Button size="xs" variant="secondary" onClick={() => setAdding(true)}>Add space</Button>}>
      {v.spaces.map((s) => editing === s.id ? (
        <SpaceForm key={s.id} initial={s} onCancel={() => setEditing(null)}
          onSave={async (d) => { await portalApi.updateSpace(token, v.id, s.id, { ...s, ...d }); setEditing(null); onChange(); }} />
      ) : (
        <div key={s.id} className="flex items-center gap-2 p-2 rounded border-2 border-border">
          <div className="flex-1 text-sm"><p className="font-bold text-text">{s.name}{!s.is_active && " (hidden)"}</p>
            <p className="text-xs text-text-muted">{s.capacity_seated ?? 0} seated · {s.capacity_standing ?? 0} standing · {s.price_from_kobo ? naira(s.price_from_kobo) : "on request"}</p></div>
          {canManage(v) && <>
            <Button size="xs" variant="secondary" onClick={() => setEditing(s.id)}>Edit</Button>
            <Button size="xs" variant="ghost" aria-label={`Remove ${s.name}`} onClick={async () => { if (confirm(`Remove ${s.name}?`)) { await portalApi.deleteSpace(token, v.id, s.id); onChange(); } }}><Trash2 size={12} /></Button>
          </>}
        </div>
      ))}
      {adding && <SpaceForm onCancel={v.spaces.length ? () => setAdding(false) : undefined}
        onSave={async (d) => { await portalApi.addSpace(token, v.id, d); setAdding(false); onChange(); }} />}
    </Card>
  );
}

function MediaCard({ v }: { v: PortalVenue }) {
  const { token, refresh } = useVenue(v.id);
  const photoInput = useRef<HTMLInputElement>(null);
  const videoInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const photos = v.media.filter((m) => m.kind === "photo").length;
  const videos = v.media.filter((m) => m.kind === "video").length;
  async function add(kind: "photo" | "video", file: File) {
    setBusy(kind); setErr("");
    try {
      if (kind === "photo") {
        const url = await uploadImage(token, file);
        await portalApi.addMedia(token, v.id, { kind, url });
      } else {
        const r = await portalApi.uploadVideo(token, file);
        await portalApi.addMedia(token, v.id, { kind, url: r.url, poster_url: r.poster_url, duration_s: r.duration_s });
      }
      refresh();
    } catch (e) { setErr(apiErrorMessage(e, "Upload failed.")); } finally { setBusy(""); }
  }
  async function move(i: number, dir: -1 | 1) {
    const ids = v.media.map((m) => m.id);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    await portalApi.reorderMedia(token, v.id, ids);
    refresh();
  }
  return (
    <Card title={`Photos ${photos}/${v.limits.photos} · Videos ${videos}/${v.limits.videos}`} actions={canManage(v) && (
      <div className="flex gap-2">
        <Button size="xs" variant="secondary" loading={busy === "photo"} disabled={photos >= v.limits.photos} onClick={() => photoInput.current?.click()}><Upload size={12} /> Photo</Button>
        <Button size="xs" variant="secondary" loading={busy === "video"} disabled={videos >= v.limits.videos} onClick={() => videoInput.current?.click()}><Upload size={12} /> Video</Button>
      </div>)}>
      <input ref={photoInput} type="file" accept="image/*" hidden onChange={(e) => e.target.files?.[0] && add("photo", e.target.files[0])} />
      <input ref={videoInput} type="file" accept="video/mp4,video/quicktime,video/webm" hidden onChange={(e) => e.target.files?.[0] && add("video", e.target.files[0])} />
      <p className="text-[11px] text-text-muted">The first photo is your cover. Videos up to 60 seconds. {v.pro.active ? "" : "Venue Pro raises the limits to 12 photos and 5 videos."}</p>
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
        {v.media.map((m, i) => (
          <div key={m.id} className={`relative rounded border-2 border-border overflow-hidden ${m.hidden ? "opacity-40" : ""}`}>
            {m.kind === "photo" ? <img src={m.url} alt="" className="w-full h-20 object-cover" />
              : <video src={m.url} poster={m.poster_url ?? undefined} className="w-full h-20 object-cover bg-black" />}
            {canManage(v) && (
              <div className="absolute inset-x-0 bottom-0 flex justify-between bg-black/60 text-white">
                <button aria-label="Move earlier" onClick={() => move(i, -1)} className="px-1"><GripVertical size={12} /></button>
                <button aria-label="Delete" onClick={async () => { await portalApi.deleteMedia(token, v.id, m.id); refresh(); }} className="px-1"><Trash2 size={12} /></button>
              </div>
            )}
            {m.hidden && <span className="absolute top-0 left-0 bg-black/70 text-white text-[9px] px-1">Hidden</span>}
          </div>
        ))}
      </div>
      {err && <p className="text-xs text-error">{err}</p>}
    </Card>
  );
}

// ── Verification ───────────────────────────────────────────────────────────────

const DOC_KINDS = [["cac", "CAC certificate"], ["owner_id", "Owner or manager ID"], ["site_photo", "Site photo"],
  ["site_video", "Site video"], ["other", "Other"]] as const;

export function VerificationTab({ v }: { v: PortalVenue }) {
  const { token, setVenue, refresh } = useVenue(v.id);
  const owner = isOwner(v);
  const locked = ["documents_approved", "visit_passed"].includes(v.verification_status);
  const [legal, setLegal] = useState({ legal_name: v.legal_name ?? "", cac_number: v.cac_number ?? "", registered_address: v.registered_address ?? "" });
  const [kind, setKind] = useState("cac");
  const [bank, setBank] = useState({ bank_code: "", account_number: "" });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");
  const banks = useQuery({ queryKey: ["banks"], queryFn: () => portalApi.banks(token), enabled: owner, staleTime: 3_600_000 });
  const docInput = useRef<HTMLInputElement>(null);

  if (!owner) return <p className="text-sm text-text-muted">Only the Owner can see verification and payout details.</p>;
  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key); setMsg("");
    try { await fn(); } catch (e) { setMsg(apiErrorMessage(e, "Something went wrong.")); } finally { setBusy(""); }
  };
  return (
    <div className="space-y-4">
      <Card title="Registered business">
        <fieldset disabled={locked} className="grid sm:grid-cols-2 gap-3">
          <label className={labelCls}>Registered name (as on CAC)<input className={fieldCls} value={legal.legal_name} onChange={(e) => setLegal({ ...legal, legal_name: e.target.value })} /></label>
          <label className={labelCls}>CAC number (RC/BN)<input className={fieldCls} value={legal.cac_number} onChange={(e) => setLegal({ ...legal, cac_number: e.target.value })} /></label>
          <label className={`${labelCls} sm:col-span-2`}>Registered address<input className={fieldCls} value={legal.registered_address} onChange={(e) => setLegal({ ...legal, registered_address: e.target.value })} /></label>
        </fieldset>
        {locked ? <p className="text-[11px] text-text-muted">Locked after verification. Contact support to change.</p>
          : <Button size="sm" loading={busy === "legal"} onClick={() => run("legal", async () => setVenue(await portalApi.update(token, v.id, legal)))}>Save</Button>}
      </Card>
      <Card title="Documents">
        <p className="text-[11px] text-text-muted">Kept privately: only Turnup admins and the agent who visits you can see them. Every view is logged. Deleted 12 months after you close the venue.</p>
        {v.documents.map((d) => (
          <div key={d.id} className="flex items-center gap-2 text-sm">
            <span className="flex-1 text-text">{DOC_KINDS.find(([k]) => k === d.kind)?.[1]} · {d.original_filename}</span>
            <span className={`text-[10px] font-black uppercase ${d.status === "approved" ? "text-success" : d.status === "rejected" ? "text-error" : "text-text-muted"}`}>{d.status}</span>
            {d.status !== "approved" && <button aria-label="Remove" onClick={() => run("del", async () => { await portalApi.deleteDocument(token, v.id, d.id); refresh(); })}><Trash2 size={13} className="text-text-muted" /></button>}
            {d.rejection_reason && <span className="w-full text-xs text-error">{d.rejection_reason}</span>}
          </div>
        ))}
        <div className="flex gap-2">
          <select className={`${fieldCls} w-auto`} value={kind} onChange={(e) => setKind(e.target.value)}>
            {DOC_KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <Button size="sm" variant="secondary" loading={busy === "doc"} onClick={() => docInput.current?.click()}><Upload size={13} /> Upload</Button>
          <input ref={docInput} type="file" hidden accept={kind === "site_video" ? "video/*" : "image/*,application/pdf"}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) run("doc", async () => { await portalApi.uploadDocument(token, v.id, kind, f); refresh(); }); e.target.value = ""; }} />
        </div>
      </Card>
      <Card title="Payout bank account">
        {v.bank.ready ? (
          <p className="text-sm text-text">{v.bank.bank_name} ····{v.bank.account_last4} · {v.bank.account_name}
            {v.bank.name_match === false && <span className="block text-xs text-warning font-bold">The account name doesn't match your registered name; Turnup will check it.</span>}</p>
        ) : <p className="text-xs text-text-muted">Payments from organizers are split by Paystack: your share goes straight to this account.</p>}
        <div className="grid sm:grid-cols-3 gap-2">
          <select className={fieldCls} value={bank.bank_code} onChange={(e) => setBank({ ...bank, bank_code: e.target.value })}>
            <option value="">Bank…</option>{banks.data?.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}</select>
          <input className={fieldCls} inputMode="numeric" maxLength={10} placeholder="10-digit account number" value={bank.account_number}
            onChange={(e) => setBank({ ...bank, account_number: e.target.value.replace(/\D/g, "") })} />
          <Button size="sm" loading={busy === "bank"} disabled={!bank.bank_code || bank.account_number.length !== 10}
            onClick={() => run("bank", async () => setVenue(await portalApi.setBank(token, v.id, bank.bank_code, bank.account_number)))}>
            {v.bank.ready ? "Change account" : "Verify and save"}</Button>
        </div>
      </Card>
      {msg && <p className="text-xs text-error">{msg}</p>}
    </div>
  );
}
