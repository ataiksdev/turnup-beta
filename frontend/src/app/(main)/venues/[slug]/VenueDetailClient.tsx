"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  BadgeCheck, CalendarDays, Gift, Heart, MapPin, MessageSquare, ShieldAlert, Star, Users,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage } from "@/lib/api";
import {
  bookingsApi, isPlus, naira, plusApi, priceLabel, VENUE_TYPES, venuesApi, type Space,
} from "@/lib/marketplace";
import { routes } from "@/lib/routes";
import { useRouteParam } from "@/lib/useRouteParam";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";

function spacePrice(s: Space) {
  if (!s.price_from_kobo) return "Price on request";
  const unit = { per_day: "/day", per_hour: "/hour", per_event: "/event" }[s.price_unit];
  return s.price_to_kobo && s.price_to_kobo !== s.price_from_kobo
    ? `${naira(s.price_from_kobo)}–${naira(s.price_to_kobo)}${unit}` : `${naira(s.price_from_kobo)}${unit}`;
}

function EnquiryForm({ slug, spaces, onDone }: { slug: string; spaces: Space[]; onDone: (id: string) => void }) {
  const { token } = useAuthStore();
  const [spaceId, setSpaceId] = useState(spaces[0]?.id ?? "");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [guests, setGuests] = useState("");
  const [eventType, setEventType] = useState("");
  const [budget, setBudget] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const send = useMutation({
    mutationFn: () => bookingsApi.enquire(token!, slug, {
      space_id: spaceId || null, starts_at: new Date(start).toISOString(), ends_at: new Date(end).toISOString(),
      guest_count: Number(guests), event_type: eventType || undefined,
      budget_kobo: budget ? Number(budget) * 100 : null, message,
    }),
    onSuccess: (e) => onDone(e.id),
    onError: (err) => setError(apiErrorMessage(err, "Couldn't send the enquiry. Try again.")),
  });
  const field = "w-full h-10 rounded border-2 border-border bg-bg px-3 text-sm text-text";
  return (
    <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); setError(""); send.mutate(); }}>
      {spaces.length > 1 && (
        <label className="block text-[11px] font-bold uppercase text-text-secondary space-y-1">Space
          <select value={spaceId} onChange={(e) => setSpaceId(e.target.value)} className={field}>
            {spaces.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
      )}
      <div className="grid grid-cols-2 gap-2">
        <label className="text-[11px] font-bold uppercase text-text-secondary space-y-1">Starts
          <input required type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className={field} /></label>
        <label className="text-[11px] font-bold uppercase text-text-secondary space-y-1">Ends
          <input required type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className={field} /></label>
        <label className="text-[11px] font-bold uppercase text-text-secondary space-y-1">Guests
          <input required type="number" min={1} value={guests} onChange={(e) => setGuests(e.target.value)} className={field} /></label>
        <label className="text-[11px] font-bold uppercase text-text-secondary space-y-1">Budget (₦, optional)
          <input type="number" min={0} value={budget} onChange={(e) => setBudget(e.target.value)} className={field} /></label>
      </div>
      <label className="block text-[11px] font-bold uppercase text-text-secondary space-y-1">Type of event
        <input value={eventType} onChange={(e) => setEventType(e.target.value)} maxLength={80}
          placeholder="Wedding, concert, product launch…" className={field} /></label>
      <label className="block text-[11px] font-bold uppercase text-text-secondary space-y-1">Message
        <textarea required value={message} onChange={(e) => setMessage(e.target.value)} rows={3} maxLength={4000}
          className="w-full rounded border-2 border-border bg-bg px-3 py-2 text-sm text-text normal-case" /></label>
      {error && <p className="text-xs text-error">{error}</p>}
      <Button type="submit" fullWidth loading={send.isPending}>Send enquiry</Button>
      <p className="text-[11px] text-text-muted">The venue replies in a Turnup thread and sends you a quote. Contact details are shared once you've booked.</p>
    </form>
  );
}

export function VenueDetailClient() {
  const slug = useRouteParam("slug");
  const router = useRouter();
  const qc = useQueryClient();
  const { token, user } = useAuthStore();
  const [reviewKind, setReviewKind] = useState<"organizer" | "guest">("organizer");
  const [showEnquiry, setShowEnquiry] = useState(false);
  const [dealCodes, setDealCodes] = useState<Record<string, string>>({});
  const [dealError, setDealError] = useState("");

  const { data: v, isPending, error } = useQuery({
    queryKey: ["venue", slug, !!token], queryFn: () => venuesApi.get(slug, token), enabled: !!slug,
  });
  const reviews = useQuery({ queryKey: ["venue", slug, "reviews", reviewKind], queryFn: () => venuesApi.reviews(slug, reviewKind), enabled: !!v });
  const events = useQuery({ queryKey: ["venue", slug, "events"], queryFn: () => venuesApi.events(slug), enabled: !!v });

  const follow = useMutation({
    mutationFn: () => (v!.is_following ? venuesApi.unfollow(token!, slug) : venuesApi.follow(token!, slug)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["venue", slug] }),
  });

  if (isPending) return <div><TopBar back /><div className="h-64 m-4 rounded border-2 border-border bg-bg-card animate-pulse" /></div>;
  if (error || !v) return <div><TopBar back title="Venue" /><p className="p-6 text-sm text-text-muted">This venue isn't available.</p></div>;

  const isOrganizer = user && ["organizer", "admin", "moderator"].includes(user.role ?? "");
  const photos = v.media.filter((m) => m.kind === "photo");
  const videos = v.media.filter((m) => m.kind === "video");

  async function claim(dealId: string) {
    setDealError("");
    try {
      const r = await plusApi.claim(token!, dealId);
      setDealCodes((c) => ({ ...c, [dealId]: r.code }));
    } catch (err) {
      setDealError(apiErrorMessage(err, "Couldn't claim that deal."));
    }
  }

  return (
    <div className="pb-24">
      <TopBar back title={v.name} />
      <div className="flex gap-2 overflow-x-auto snap-x">
        {(photos.length ? photos : [{ id: "c", url: v.cover_image ?? "" }]).map((p) => (
          <div key={p.id} className="snap-start shrink-0 w-full h-60 bg-bg-elevated">
            {p.url ? <img src={p.url} alt="" className="w-full h-full object-cover" /> : null}
          </div>
        ))}
      </div>

      <div className="px-4 py-4 space-y-5">
        <header className="space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            {v.featured && <span className="px-1.5 py-0.5 rounded bg-primary text-on-primary text-[10px] font-black uppercase">Featured</span>}
            {v.is_pro && <span className="px-1.5 py-0.5 rounded border border-border text-[10px] font-black uppercase">Pro</span>}
            <span className="text-[10px] font-black uppercase tracking-wide text-text-muted">
              {VENUE_TYPES.find((t) => t.id === v.type)?.label}</span>
          </div>
          <h1 className="text-xl font-black text-text flex items-center gap-1.5">
            {v.name}{v.is_verified && <BadgeCheck size={18} className="text-primary" aria-label="Visited by Turnup" />}
          </h1>
          <p className="text-xs text-text-secondary flex items-center gap-1"><MapPin size={12} aria-hidden />
            {[v.area, v.state === "FCT" ? "Abuja" : v.state].filter(Boolean).join(", ")}</p>
          <div className="flex items-center gap-3 text-xs text-text-secondary">
            <span className="flex items-center gap-1"><Users size={12} aria-hidden /> Up to {v.capacity.toLocaleString()}</span>
            <span className="font-bold text-text">{priceLabel(v.price)}</span>
          </div>
          <div className="flex gap-3 text-xs">
            <span><Star size={12} className="inline text-warning" aria-hidden /> {v.rating_organizers?.toFixed(1) ?? "–"} for organizers ({v.reviews_organizers_count})</span>
            <span><Star size={12} className="inline text-warning" aria-hidden /> {v.rating_guests?.toFixed(1) ?? "–"} for guests ({v.reviews_guests_count})</span>
          </div>
        </header>

        <div className="flex gap-2">
          {token && (
            <Button variant={v.is_following ? "secondary" : "outline"} size="sm" loading={follow.isPending}
              onClick={() => follow.mutate()}>
              <Heart size={14} className={cn(v.is_following && "fill-current")} aria-hidden />
              {v.is_following ? "Following" : "Follow"} · {v.followers_count}
            </Button>
          )}
          {v.accepting_enquiries && (
            isOrganizer
              ? <Button size="sm" onClick={() => setShowEnquiry((s) => !s)}><MessageSquare size={14} aria-hidden /> Enquire</Button>
              : <Link href={token ? "/onboarding/organizer" : `/login?next=${encodeURIComponent(routes.venue(slug))}`}
                  className="text-xs font-bold text-primary underline self-center">Become an organizer to book</Link>
          )}
        </div>

        {!v.accepting_enquiries && (
          <p className="flex items-start gap-2 p-3 rounded border-2 border-warning/50 bg-warning/10 text-xs text-text">
            <ShieldAlert size={14} className="shrink-0 mt-0.5" aria-hidden /> Not currently accepting bookings.
          </p>
        )}
        {v.accepting_enquiries && !v.deposits_enabled && (
          <p className="text-[11px] text-text-muted">Turnup hasn't visited this venue yet. You can enquire now; payment opens after the visit.</p>
        )}

        {showEnquiry && (
          <section className="p-3 rounded border-2 border-primary bg-bg-card">
            <EnquiryForm slug={slug} spaces={v.spaces} onDone={(id) => router.push(routes.enquiry(id))} />
          </section>
        )}

        {v.description && <p className="text-sm text-text-secondary whitespace-pre-wrap">{v.description}</p>}

        {videos.length > 0 && (
          <section className="space-y-2" aria-label="Videos">
            {videos.map((m) => (
              <video key={m.id} src={m.url} poster={m.poster_url ?? undefined} controls preload="metadata"
                className="w-full rounded border-2 border-border bg-black" />
            ))}
          </section>
        )}

        <section className="space-y-2">
          <h2 className="text-xs font-black uppercase tracking-widest text-text">Spaces</h2>
          {v.spaces.map((s) => (
            <div key={s.id} className="p-3 rounded border-2 border-border bg-bg-card">
              <div className="flex justify-between gap-2">
                <p className="text-sm font-bold text-text">{s.name}</p>
                <p className="text-xs font-bold text-text">{v.price.display === "on_request" ? "On request" : spacePrice(s)}</p>
              </div>
              <p className="text-xs text-text-muted">
                {[s.capacity_seated && `${s.capacity_seated} seated`, s.capacity_standing && `${s.capacity_standing} standing`, s.setting]
                  .filter(Boolean).join(" · ")}
              </p>
              {s.description && <p className="text-xs text-text-secondary mt-1">{s.description}</p>}
            </div>
          ))}
        </section>

        {!!v.amenities.length && (
          <section className="space-y-2">
            <h2 className="text-xs font-black uppercase tracking-widest text-text">Amenities</h2>
            <div className="flex flex-wrap gap-1.5">
              {v.amenities.map((a) => <span key={a} className="px-2 py-0.5 rounded border border-border text-xs text-text-secondary">{a}</span>)}
            </div>
          </section>
        )}

        <section className="space-y-1 text-xs text-text-secondary">
          <h2 className="text-xs font-black uppercase tracking-widest text-text">Booking terms</h2>
          <p>Deposit: {v.deposit_type === "percent" ? `${v.deposit_value}% of the quote` : naira(v.deposit_value)}.
            Balance due {v.balance_due_days} days before, paid through Turnup.</p>
          <p>{v.refund_policy}. Refunds are paid by the venue.</p>
          {v.cancellations_last_year > 0 && (
            <p className="text-warning font-bold">{v.cancellations_last_year} cancellation{v.cancellations_last_year > 1 ? "s" : ""} by the venue in the last 12 months</p>
          )}
          {v.rules && <p className="whitespace-pre-wrap">{v.rules}</p>}
        </section>

        {!!v.deals.length && (
          <section className="space-y-2">
            <h2 className="text-xs font-black uppercase tracking-widest text-text flex items-center gap-1.5"><Gift size={13} aria-hidden /> Turnup+ deals</h2>
            {v.deals.map((d) => (
              <div key={d.id} className="p-3 rounded border-2 border-border bg-bg-card flex items-center gap-3">
                <div className="flex-1">
                  <p className="text-sm font-bold text-text">{d.title}</p>
                  {d.description && <p className="text-xs text-text-muted">{d.description}</p>}
                </div>
                {dealCodes[d.id]
                  ? <span className="font-mono font-black text-primary">{dealCodes[d.id]}</span>
                  : isPlus(user)
                    ? <Button size="xs" onClick={() => claim(d.id)}>Get code</Button>
                    : <Link href="/plus" className="text-xs font-bold text-primary underline">Join Turnup+</Link>}
              </div>
            ))}
            {dealError && <p className="text-xs text-error">{dealError}</p>}
          </section>
        )}

        {!!events.data?.length && (
          <section className="space-y-2">
            <h2 className="text-xs font-black uppercase tracking-widest text-text flex items-center gap-1.5"><CalendarDays size={13} aria-hidden /> Events here</h2>
            {events.data.map((e) => (
              <Link key={e.id} href={routes.event(e.slug)} className="flex gap-3 p-2 rounded border-2 border-border bg-bg-card hover:border-primary">
                <div className="w-14 h-14 rounded bg-bg-elevated overflow-hidden shrink-0">
                  {e.cover_image && <img src={e.cover_image} alt="" className="w-full h-full object-cover" />}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-bold text-text truncate">{e.title}</p>
                  <p className="text-xs text-text-muted">{format(new Date(e.start_date), "EEE d MMM, h:mm a")}</p>
                  {e.members_only && <p className="text-[10px] font-black uppercase text-primary">Turnup+ members</p>}
                </div>
              </Link>
            ))}
          </section>
        )}

        <section className="space-y-2">
          <div className="flex gap-2" role="tablist" aria-label="Reviews">
            {(["organizer", "guest"] as const).map((k) => (
              <button key={k} role="tab" aria-selected={reviewKind === k} onClick={() => setReviewKind(k)}
                className={cn("px-2.5 py-1 rounded border-2 text-xs font-bold",
                  reviewKind === k ? "bg-text text-bg border-border" : "border-border-subtle text-text-secondary")}>
                {k === "organizer" ? "From organizers" : "From guests"}
              </button>
            ))}
          </div>
          {reviews.data?.length === 0 && <p className="text-xs text-text-muted">No reviews yet.</p>}
          {reviews.data?.map((r) => (
            <div key={r.id} className="p-3 rounded border-2 border-border bg-bg-card space-y-1">
              <div className="flex items-center gap-2 text-xs">
                <span className="font-bold text-text">{r.author.display_name ?? r.author.username}</span>
                {r.author.is_plus && <span className="px-1 rounded bg-primary text-on-primary text-[9px] font-black">PLUS</span>}
                <span className="ml-auto text-warning">{"★".repeat(r.rating)}{"☆".repeat(5 - r.rating)}</span>
              </div>
              {r.body && <p className="text-sm text-text-secondary">{r.body}</p>}
              {r.venue_reply && <p className="text-xs text-text-muted border-l-2 border-primary pl-2">Venue: {r.venue_reply}</p>}
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
