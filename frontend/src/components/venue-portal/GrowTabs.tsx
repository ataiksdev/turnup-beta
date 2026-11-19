"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import Link from "next/link";
import { useState } from "react";
import { VenueDealsManager } from "@/components/organizer/EventDealsManager";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage } from "@/lib/api";
import { goToPayment, naira, paymentCallback, portalApi, type PortalVenue, type VenueRole } from "@/lib/marketplace";
import { routes } from "@/lib/routes";
import { Card, canManage, fieldCls, isOwner, labelCls, useVenue } from "./shared";

// ── Team ───────────────────────────────────────────────────────────────────────

export function TeamTab({ v }: { v: PortalVenue }) {
  const { token } = useVenue(v.id);
  const qc = useQueryClient();
  const key = ["portal", v.id, "members"];
  const { data } = useQuery({ queryKey: key, queryFn: () => portalApi.members(token, v.id) });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"manager" | "viewer">("manager");
  const [msg, setMsg] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const act = (fn: () => Promise<unknown>) => fn().then(refresh).catch((e) => setMsg(apiErrorMessage(e, "Couldn't do that.")));
  return (
    <div className="space-y-4">
      <Card title={`Team (${(data?.members.length ?? 0) + (data?.invites.length ?? 0)} of ${data?.seats ?? "?"} seats)`}>
        <p className="text-[11px] text-text-muted">Owner: everything. Manager: listing, calendar, enquiries, quotes, bookings, events, deals. Viewer: read-only and door check-in.</p>
        {data?.members.map((m) => (
          <div key={m.user.id} className="flex items-center gap-2 text-sm">
            <span className="flex-1 text-text">{m.user.display_name ?? m.user.username} <span className="text-text-muted">@{m.user.username}</span></span>
            {isOwner(v) && m.role !== "owner" ? (
              <>
                <select className={`${fieldCls} w-auto h-8`} value={m.role} onChange={(e) => act(() => portalApi.setRole(token, v.id, m.user.id, e.target.value as VenueRole))}>
                  <option value="manager">Manager</option><option value="viewer">Viewer</option>
                  {m.role === "manager" && <option value="owner">Make Owner</option>}
                </select>
                <Button size="xs" variant="ghost" onClick={() => act(() => portalApi.removeMember(token, v.id, m.user.id))}>Remove</Button>
              </>
            ) : <span className="text-[10px] font-black uppercase text-text-secondary">{m.role}</span>}
          </div>
        ))}
        {data?.invites.map((i) => (
          <div key={i.id} className="flex items-center gap-2 text-sm text-text-muted">
            <span className="flex-1">{i.email} · invited as {i.role}</span>
            {isOwner(v) && <Button size="xs" variant="ghost" onClick={() => act(() => portalApi.revokeInvite(token, v.id, i.id))}>Revoke</Button>}
          </div>
        ))}
      </Card>
      {isOwner(v) && (
        <Card title="Invite">
          <div className="flex gap-2">
            <input className={fieldCls} type="email" placeholder="Their email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <select className={`${fieldCls} w-auto`} value={role} onChange={(e) => setRole(e.target.value as "manager" | "viewer")}>
              <option value="manager">Manager</option><option value="viewer">Viewer</option></select>
            <Button size="sm" disabled={!email.includes("@")} onClick={() => act(async () => {
              const r = await portalApi.invite(token, v.id, email, role);
              setEmail(""); setMsg(r.link ? `Invitation sent. (Dev link: ${r.link})` : "Invitation sent.");
            })}>Invite</Button>
          </div>
        </Card>
      )}
      {msg && <p className="text-xs text-text-secondary break-all">{msg}</p>}
      {isOwner(v) && (
        <Card title="Close this venue">
          <p className="text-[11px] text-text-muted">Possible once there are no upcoming bookings, unpaid refunds or balance. Verification files are deleted 12 months later.</p>
          <Button size="xs" variant="danger" onClick={() => { if (confirm("Close this venue? It disappears from Turnup.")) act(() => portalApi.close(token, v.id)); }}>Close venue</Button>
        </Card>
      )}
    </div>
  );
}

// ── Deals, reviews, events ─────────────────────────────────────────────────────

export function DealsTab({ v }: { v: PortalVenue }) {
  const { token } = useVenue(v.id);
  const [code, setCode] = useState("");
  const [result, setResult] = useState("");
  return (
    <div className="space-y-4">
      <Card title="Check a member's code">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); portalApi.redeem(token, v.id, code.trim())
          .then((r) => setResult(r.ok ? `Valid: ${r.deal} for ${r.member}` : `Not valid: ${r.reason?.replace(/_/g, " ")}`))
          .catch((x) => setResult(apiErrorMessage(x, "Code not found."))); setCode(""); }}>
          <input className={`${fieldCls} font-mono uppercase`} value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="CODE" maxLength={12} />
          <Button type="submit" size="sm" disabled={!code.trim()}>Check</Button>
        </form>
        {result && <p role="status" className="text-sm font-bold text-text">{result}</p>}
      </Card>
      {canManage(v) && <Card title="Turnup+ member deals"><VenueDealsManager venueId={v.id} /></Card>}
    </div>
  );
}

export function ReviewsTab({ v }: { v: PortalVenue }) {
  const { token } = useVenue(v.id);
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["portal", v.id, "reviews"], queryFn: () => portalApi.reviews(token, v.id) });
  const [replies, setReplies] = useState<Record<string, string>>({});
  if (data?.length === 0) return <p className="text-sm text-text-muted">No reviews yet.</p>;
  return (
    <div className="space-y-2">
      {data?.map((r) => (
        <Card key={r.id}>
          <p className="text-xs text-text-muted">{r.kind === "organizer" ? "Organizer" : "Guest"} · {r.author.display_name ?? r.author.username} · {format(new Date(r.created_at), "d MMM yyyy")}{r.is_hidden && " · hidden by Turnup"}</p>
          <p className="text-warning">{"★".repeat(r.rating)}{"☆".repeat(5 - r.rating)}</p>
          {r.body && <p className="text-sm text-text">{r.body}</p>}
          {r.venue_reply ? <p className="text-xs text-text-secondary border-l-2 border-primary pl-2">Your reply: {r.venue_reply}</p> : canManage(v) && (
            <div className="flex gap-2">
              <input className={fieldCls} placeholder="Reply publicly" value={replies[r.id] ?? ""} onChange={(e) => setReplies({ ...replies, [r.id]: e.target.value })} />
              <Button size="xs" disabled={!replies[r.id]?.trim()} onClick={() => portalApi.reply(token, v.id, r.id, replies[r.id]).then(() => qc.invalidateQueries({ queryKey: ["portal", v.id, "reviews"] }))}>Reply</Button>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}

export function EventsTab({ v }: { v: PortalVenue }) {
  const { token } = useVenue(v.id);
  const qc = useQueryClient();
  const key = ["portal", v.id, "events"];
  const { data } = useQuery({ queryKey: key, queryFn: () => portalApi.events(token, v.id) });
  const [f, setF] = useState({ title: "", description: "", start: "", end: "", members_only: false, fast_lane: false });
  const [err, setErr] = useState("");
  const create = useMutation({
    mutationFn: () => portalApi.createEvent(token, v.id, {
      title: f.title, description: f.description, start_date: new Date(f.start).toISOString(), end_date: new Date(f.end).toISOString(),
      members_only: f.members_only, fast_lane_enabled: f.fast_lane, status: "published",
    }),
    onSuccess: () => { setF({ title: "", description: "", start: "", end: "", members_only: false, fast_lane: false }); qc.invalidateQueries({ queryKey: key }); },
    onError: (e) => setErr(apiErrorMessage(e, "Couldn't create the event.")),
  });
  return (
    <div className="space-y-4">
      {canManage(v) && v.status === "live" && (
        <Card title="New event hosted by the venue">
          <p className="text-[11px] text-text-muted">It shows {v.name} as the host. Followers are alerted once Turnup approves it (Turnup+ members first). Invite organizers as co-hosts and add tickets from the event's manage page.</p>
          <div className="grid sm:grid-cols-2 gap-2">
            <label className={`${labelCls} sm:col-span-2`}>Title<input className={fieldCls} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
            <label className={`${labelCls} sm:col-span-2`}>Description<textarea rows={3} className={`${fieldCls} h-auto py-2`} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
            <label className={labelCls}>Starts<input type="datetime-local" className={fieldCls} value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></label>
            <label className={labelCls}>Ends<input type="datetime-local" className={fieldCls} value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></label>
            <label className="flex items-center gap-2 text-sm text-text"><input type="checkbox" checked={f.members_only} onChange={(e) => setF({ ...f, members_only: e.target.checked })} /> Turnup+ members only</label>
            <label className="flex items-center gap-2 text-sm text-text"><input type="checkbox" checked={f.fast_lane} onChange={(e) => setF({ ...f, fast_lane: e.target.checked })} /> Fast lane for members</label>
          </div>
          <Button size="sm" loading={create.isPending} disabled={f.title.length < 5 || f.description.length < 20 || !f.start || !f.end} onClick={() => { setErr(""); create.mutate(); }}>Create event</Button>
          {err && <p className="text-xs text-error">{err}</p>}
        </Card>
      )}
      <Card title="Events">
        {data?.length === 0 && <p className="text-sm text-text-muted">No events yet.</p>}
        {data?.map((e) => (
          <div key={e.id} className="flex items-center gap-2 text-sm">
            <span className="flex-1"><Link href={routes.event(e.slug)} className="font-bold text-text hover:text-primary">{e.title}</Link>
              <span className="block text-xs text-text-muted">{format(new Date(e.start_date), "d MMM yyyy")} · {e.review_status === "approved" ? e.status : `review ${e.review_status}`} · {e.attendees_count} going</span></span>
            <Link href={routes.organizerEvent(e.id, "edit")} className="text-xs font-bold text-primary underline">Manage</Link>
            <Link href={routes.organizerEvent(e.id, "checkin")} className="text-xs font-bold text-primary underline">Check-in</Link>
          </div>
        ))}
      </Card>
    </div>
  );
}

// ── Pro, featured, analytics ───────────────────────────────────────────────────

export function GrowTab({ v }: { v: PortalVenue }) {
  const { token } = useVenue(v.id);
  const [err, setErr] = useState("");
  const [scope, setScope] = useState<"state" | "area">("area");
  const [weeks, setWeeks] = useState<string[]>([]);
  const plans = useQuery({ queryKey: ["portal", "plans"], queryFn: portalApi.plans });
  const featured = useQuery({ queryKey: ["portal", v.id, "featured"], queryFn: () => portalApi.featured(token, v.id), enabled: canManage(v) });
  const analytics = useQuery({ queryKey: ["portal", v.id, "analytics"], queryFn: () => portalApi.analytics(token, v.id), enabled: v.pro.active, retry: false });
  const back = paymentCallback(`/venue/manage?id=${v.id}&tab=grow`);
  const fail = (e: unknown) => setErr(apiErrorMessage(e, "Couldn't start the payment."));
  const f = featured.data;
  const price = f ? (scope === "state" ? f.price_state_kobo : f.price_area_kobo) : 0;
  return (
    <div className="space-y-4">
      <Card title="Venue Pro">
        {v.pro.active ? (
          <div className="space-y-2">
            <p className="text-sm text-text">Active until {v.pro.until && format(new Date(v.pro.until), "d MMM yyyy")}{v.pro.status === "non_renewing" && " (won't renew)"}.</p>
            {isOwner(v) && v.pro.status === "active" && <Button size="xs" variant="ghost" onClick={() => portalApi.cancelPro(token, v.id).catch(fail)}>Cancel renewal</Button>}
          </div>
        ) : (
          <>
            <p className="text-sm text-text-secondary">12 photos and 5 videos (instead of 6 and 2), analytics, a ranking boost in search, 10 team seats and a Pro badge.</p>
            {isOwner(v) && <div className="flex flex-wrap gap-2">
              {plans.data?.filter((p) => p.product === "venue_pro").map((p) => (
                <Button key={p.code} size="sm" variant={p.interval === "annually" ? "secondary" : "primary"}
                  onClick={() => portalApi.subscribePro(token, v.id, p.code, back).then(goToPayment).catch(fail)}>
                  {naira(p.amount_kobo)} / {p.interval === "annually" ? "year" : "month"}</Button>
              ))}
            </div>}
          </>
        )}
      </Card>
      {canManage(v) && f && (
        <Card title="Featured placement">
          <p className="text-[11px] text-text-muted">Shown in the Featured strip and pinned at the top of matching searches for a week (Monday to Sunday).
            State-wide: {naira(f.price_state_kobo)}/week across {f.state}. Area: {naira(f.price_area_kobo)}/week in {f.area ?? "your area"}, shown when people pick your area or search near you.</p>
          <div className="flex gap-2">
            {(["area", "state"] as const).map((s) => (
              <button key={s} disabled={s === "area" && !f.area_available} onClick={() => { setScope(s); setWeeks([]); }}
                className={`px-3 py-1.5 rounded border-2 text-xs font-bold ${scope === s ? "border-primary bg-primary/10 text-text" : "border-border text-text-secondary"} disabled:opacity-40`}>
                {s === "area" ? `Area · ${f.area ?? "n/a"}` : `State-wide · ${f.state}`}</button>
            ))}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {f.weeks.map((w) => {
              const left = scope === "state" ? w.state_left : w.area_left;
              const mine = f.mine.some((m) => m.scope === scope && m.week_start.slice(0, 10) === w.week_start);
              const on = weeks.includes(w.week_start);
              return (
                <button key={w.week_start} disabled={!left || mine} onClick={() => setWeeks(on ? weeks.filter((x) => x !== w.week_start) : [...weeks, w.week_start])}
                  className={`p-2 rounded border-2 text-left text-xs ${on ? "border-primary bg-primary/10" : "border-border"} disabled:opacity-40`}>
                  <span className="block font-bold text-text">w/c {format(new Date(w.week_start), "d MMM")}</span>
                  <span className="text-text-muted">{mine ? "Yours" : left ? `${left} left` : "Full"}</span>
                </button>
              );
            })}
          </div>
          <Button size="sm" disabled={!weeks.length || v.status !== "live"} onClick={() => portalApi.buyFeatured(token, v.id, scope, weeks, back).then(goToPayment).catch(fail)}>
            Pay {naira(price * weeks.length)}</Button>
        </Card>
      )}
      <Card title="Analytics (last 90 days)">
        {!v.pro.active ? <p className="text-sm text-text-muted">Part of Venue Pro.</p> : analytics.data && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {Object.entries({ "Profile views": analytics.data.profile_views, Enquiries: analytics.data.enquiries, Bookings: analytics.data.bookings,
              Conversion: analytics.data.conversion != null ? `${Math.round(Number(analytics.data.conversion) * 100)}%` : "–",
              "New followers": analytics.data.new_followers, Followers: analytics.data.followers,
              "Booking value": naira(Number(analytics.data.booking_value_kobo ?? 0)), "Your replies": analytics.data.venue_replies,
            }).map(([k, val]) => (
              <div key={k} className="p-2 rounded border-2 border-border"><p className="text-[10px] font-black uppercase text-text-muted">{k}</p><p className="text-lg font-black text-text">{val}</p></div>
            ))}
          </div>
        )}
      </Card>
      {err && <p className="text-xs text-error">{err}</p>}
    </div>
  );
}
