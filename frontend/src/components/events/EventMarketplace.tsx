"use client";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { BadgeCheck, Building2, Gift, Sparkles, Star } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage, type TicketTierDetail } from "@/lib/api";
import { bookingsApi, isPlus, plusApi, venuesApi } from "@/lib/marketplace";
import { routes } from "@/lib/routes";
import { useAuthStore } from "@/store/auth";
import type { Event } from "@/types";

/** "Turnup+ only" / "Members' presale" labels on a ticket tier. */
export function TierPlusBadges({ tier }: { tier: TicketTierDetail }) {
  const presale = tier.plus_presale_ends_at && new Date(tier.plus_presale_ends_at) > new Date();
  if (!tier.members_only && !presale) return null;
  return (
    <p className="mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-primary/15 text-primary text-[10px] font-black uppercase">
      <Sparkles size={10} aria-hidden />
      {tier.members_only ? "Turnup+ members" : `Members' presale until ${format(new Date(tier.plus_presale_ends_at!), "d MMM, h:mm a")}`}
    </p>
  );
}

export function MembersOnlyNotice() {
  const { user } = useAuthStore();
  if (isPlus(user)) return null;
  return (
    <div className="flex items-center gap-2 p-3 rounded border-2 border-primary bg-primary/10 text-sm text-text">
      <Sparkles size={16} className="text-primary shrink-0" aria-hidden />
      <span className="flex-1">This event is for Turnup+ members.</span>
      <Link href="/plus" className="text-xs font-black text-primary underline">Join</Link>
    </div>
  );
}

/** The venue hosting the event, or the listed venue it takes place at. */
export function EventVenueCard({ event }: { event: Event }) {
  const id = event.host_venue_id || event.venue_id;
  const { data: v } = useQuery({ queryKey: ["venue", id, "card"], queryFn: () => venuesApi.get(id!), enabled: !!id, retry: false });
  if (!v) return null;
  return (
    <Link href={routes.venue(v.slug)} className="flex items-center gap-3 p-3 rounded border-2 border-border bg-bg-card hover:border-primary">
      <div className="w-12 h-12 rounded bg-bg-elevated overflow-hidden shrink-0">
        {v.cover_image ? <img src={v.cover_image} alt="" className="w-full h-full object-cover" /> : <Building2 className="m-3 text-text-muted" />}
      </div>
      <div className="min-w-0">
        <p className="text-[10px] font-black uppercase text-text-muted">{event.host_venue_id ? "Hosted by the venue" : "Venue"}</p>
        <p className="text-sm font-bold text-text flex items-center gap-1 truncate">{v.name}
          {v.is_verified && <BadgeCheck size={14} className="text-primary" aria-label="Visited by Turnup" />}</p>
        <p className="text-xs text-text-muted">{[v.area, v.state === "FCT" ? "Abuja" : v.state].filter(Boolean).join(", ")}</p>
      </div>
    </Link>
  );
}

export function EventDeals({ eventId }: { eventId: string }) {
  const { token, user } = useAuthStore();
  const { data } = useQuery({ queryKey: ["event-deals", eventId], queryFn: () => plusApi.eventDeals(eventId) });
  const [codes, setCodes] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  if (!data?.length) return null;
  return (
    <section className="space-y-2" aria-label="Turnup+ deals">
      <h2 className="text-sm font-bold text-text flex items-center gap-2"><Gift size={16} className="text-primary" aria-hidden /> Turnup+ deals</h2>
      {data.map((d) => (
        <div key={d.id} className="p-3 rounded border-2 border-border flex items-center gap-3">
          <div className="flex-1"><p className="text-sm font-bold text-text">{d.title}</p>
            {d.description && <p className="text-xs text-text-muted">{d.description}</p>}</div>
          {codes[d.id] ? <span className="font-mono font-black text-primary">{codes[d.id]}</span>
            : isPlus(user) ? <Button size="xs" onClick={() => plusApi.claim(token!, d.id)
                .then((r) => setCodes((c) => ({ ...c, [d.id]: r.code })))
                .catch((e) => setError(apiErrorMessage(e, "Couldn't claim it.")))}>Get code</Button>
            : <Link href="/plus" className="text-xs font-bold text-primary underline">Turnup+</Link>}
        </div>
      ))}
      {error && <p className="text-xs text-error">{error}</p>}
    </section>
  );
}

/** After the event: guests whose ticket was checked in can review the venue (14 days). */
export function GuestVenueReview({ event }: { event: Event }) {
  const { token } = useAuthStore();
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done">("idle");
  const [error, setError] = useState("");
  const venueId = event.venue_id || event.host_venue_id;
  const ended = new Date(event.end_date) < new Date();
  const recent = Date.now() - new Date(event.end_date).getTime() < 14 * 86_400_000;
  if (!token || !venueId || !ended || !recent) return null;
  if (state === "done") return <p className="text-sm font-bold text-success">Thanks for reviewing the venue.</p>;
  return (
    <section className="p-3 rounded border-2 border-border space-y-2">
      <p className="text-sm font-bold text-text">Were you there? Rate the venue</p>
      <div className="flex gap-1" role="radiogroup" aria-label="Venue rating">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} role="radio" aria-checked={rating === n} onClick={() => setRating(n)}
            className={n <= rating ? "text-warning" : "text-text-muted"}><Star size={20} className={n <= rating ? "fill-current" : ""} /></button>
        ))}
      </div>
      {rating > 0 && (
        <>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={2} maxLength={3000}
            placeholder="Sound, space, staff, toilets, parking…" className="w-full rounded border-2 border-border bg-bg px-2 py-1 text-sm text-text" />
          <Button size="sm" loading={state === "sending"} onClick={async () => {
            setState("sending"); setError("");
            try { await bookingsApi.guestReview(token, event.id, rating, body || undefined); setState("done"); }
            catch (e) { setState("idle"); setError(apiErrorMessage(e, "Couldn't post the review.")); }
          }}>Post review</Button>
        </>
      )}
      {error && <p className="text-xs text-error">{error}</p>}
    </section>
  );
}
