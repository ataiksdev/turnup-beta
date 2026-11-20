"use client";
import { Suspense, useMemo } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, CheckCircle2, Heart, MapPin, PartyPopper, Star, Ticket, Bookmark, WifiOff, Clock } from "lucide-react";
import { organizerApi, usersApi, type TicketOrder } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useOfflineCopy } from "@/store/tickets";
import { useOffline } from "@/lib/network";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { OfflineImg } from "@/components/ui/OfflineImg";
import { cn, formatEventDate } from "@/lib/utils";
import { routes } from "@/lib/routes";
import type { Event } from "@/types";

/** One event on My Vibes, with everything the user has for it. */
interface Vibe {
  eventId: string;
  title: string;
  start: string | null;
  end: string | null;
  venue: string | null;
  city: string | null;
  cover: string | null;
  tickets: TicketOrder[];
  going: boolean;
  interested: boolean;
  saved: boolean;
}

// Tickets worth showing: bought (or free) and still valid, or with a refund in progress.
const SHOWN_TICKET_STATUSES = new Set(["confirmed", "needs_refund", "refunded"]);
const HOURS = 60 * 60 * 1000;

function endTime(v: Vibe): number {
  if (v.end) return new Date(v.end).getTime();
  if (v.start) return new Date(v.start).getTime() + 6 * HOURS; // ticket-only: no end date known
  return 0;
}

function buildVibes(tickets: TicketOrder[], attending: Event[], saved: Event[], kept: Record<string, Event>): Vibe[] {
  const byId = new Map<string, Vibe>();
  const get = (id: string): Vibe => {
    let v = byId.get(id);
    if (!v) {
      const e = kept[id];
      v = {
        eventId: id, title: e?.title ?? "Event", start: e?.start_date ?? null, end: e?.end_date ?? null,
        venue: e?.venue_name ?? null, city: e?.city ?? null, cover: e?.cover_image ?? null,
        tickets: [], going: false, interested: false, saved: false,
      };
      byId.set(id, v);
    }
    return v;
  };
  const fromEvent = (v: Vibe, e: Event) => {
    v.title = e.title; v.start = e.start_date; v.end = e.end_date;
    v.venue = e.venue_name; v.city = e.city; v.cover = e.cover_image ?? null;
  };
  for (const t of tickets) {
    if (!SHOWN_TICKET_STATUSES.has(t.status)) continue;
    const v = get(t.event_id);
    v.tickets.push(t);
    if (!kept[t.event_id]) {
      v.title = t.event_title ?? v.title; v.start = t.event_date ?? v.start;
      v.venue = t.event_venue ?? v.venue; v.city = t.event_city ?? v.city; v.cover = t.event_cover ?? v.cover;
    }
  }
  for (const e of attending) {
    const v = get(e.id);
    fromEvent(v, e);
    if (e.attendance_status === "going") v.going = true;
    if (e.attendance_status === "interested") v.interested = true;
  }
  for (const e of saved) {
    const v = get(e.id);
    fromEvent(v, e);
    v.saved = true;
  }
  return [...byId.values()];
}

function Chip({ icon: Icon, label, tone }: { icon: typeof Ticket; label: string; tone: "primary" | "success" | "muted" }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-black uppercase tracking-wide",
      tone === "primary" && "text-primary border-primary/40 bg-primary/10",
      tone === "success" && "text-success border-success/40 bg-success/10",
      tone === "muted" && "text-text-muted border-border-subtle bg-bg-elevated",
    )}>
      <Icon size={10} aria-hidden /> {label}
    </span>
  );
}

function VibeCard({ v, past }: { v: Vibe; past: boolean }) {
  const eventHref = routes.event(v.eventId);
  const confirmed = v.tickets.filter((t) => t.status === "confirmed");
  const ticketCount = confirmed.reduce((n, t) => n + t.quantity, 0);
  const checkedIn = v.tickets.some((t) => t.checked_in_at);
  const attended = ticketCount > 0 || v.going;
  return (
    <article className="flex gap-3 p-3 rounded border-2 border-border bg-bg-card shadow-brutal-sm">
      <Link href={eventHref} className="shrink-0 w-20 h-20 rounded overflow-hidden bg-bg-elevated" tabIndex={-1} aria-hidden>
        {v.cover
          ? <OfflineImg src={v.cover} alt="" className="w-full h-full object-cover" />
          : <div className="w-full h-full bg-gradient-to-br from-primary/30 to-bg-elevated" />}
      </Link>
      <div className="flex-1 min-w-0 space-y-1.5">
        <Link href={eventHref} className="block">
          <h3 className="font-black text-sm text-text leading-tight line-clamp-2">{v.title}</h3>
        </Link>
        <div className="space-y-0.5 text-xs text-text-muted">
          {v.start && (
            <p className="flex items-center gap-1"><CalendarDays size={11} aria-hidden /> {formatEventDate(v.start)}</p>
          )}
          {(v.venue || v.city) && (
            <p className="flex items-center gap-1 min-w-0">
              <MapPin size={11} className="shrink-0" aria-hidden />
              <span className="truncate">{[v.venue, v.city].filter(Boolean).join(" · ")}</span>
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-1">
          {ticketCount > 0 && <Chip icon={Ticket} label={ticketCount === 1 ? "Ticket" : `${ticketCount} tickets`} tone="primary" />}
          {v.tickets.some((t) => t.status !== "confirmed") && <Chip icon={Clock} label="Refund" tone="muted" />}
          {v.going && ticketCount === 0 && <Chip icon={CheckCircle2} label="Going" tone="primary" />}
          {v.interested && <Chip icon={Heart} label="Interested" tone="muted" />}
          {v.saved && <Chip icon={Bookmark} label="Saved" tone="muted" />}
          {past && ticketCount > 0 && (checkedIn
            ? <Chip icon={CheckCircle2} label="You were there" tone="success" />
            : <Chip icon={Clock} label="Not checked in" tone="muted" />)}
        </div>
        {(confirmed.length > 0 || (past && attended)) && (
          <div className="flex flex-wrap gap-2 pt-0.5">
            {!past && confirmed.map((t, i) => (
              <Link key={t.id} href={routes.ticket(t.id)}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded border-2 border-border bg-primary text-on-primary text-xs font-bold">
                <Ticket size={13} aria-hidden /> {confirmed.length > 1 ? `Ticket ${i + 1}` : "Show ticket"}
              </Link>
            ))}
            {past && attended && (
              <Link href={eventHref}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded border-2 border-border bg-bg-card text-xs font-bold text-text">
                <Star size={13} aria-hidden /> Rate this event
              </Link>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

function MyVibes() {
  const { token, user } = useAuthStore();
  const router = useRouter();
  const params = useSearchParams();
  const tab: "upcoming" | "past" = params.get("tab") === "past" ? "past" : "upcoming";
  const offline = useOffline();
  const copy = useOfflineCopy(user?.id);
  const enabled = !!token && !!user;

  const ticketsQ = useQuery({ queryKey: ["my-tickets", user?.id], queryFn: () => organizerApi.myTickets(token!), enabled });
  const savedQ = useQuery({ queryKey: ["saved", user?.username], queryFn: () => usersApi.saved(user!.username, token!, 1), enabled });
  const upcomingQ = useQuery({
    queryKey: ["attending", user?.username, "upcoming"],
    queryFn: () => usersApi.attending(user!.username, token!, false, 1, 50), enabled,
  });
  const pastQ = useQuery({
    queryKey: ["attending", user?.username, "past"],
    queryFn: () => usersApi.attending(user!.username, token!, true, 1, 50), enabled: enabled && tab === "past",
  });

  // Live data where it's loaded; otherwise the copy kept on the phone (OfflineSync).
  const tickets = ticketsQ.data ?? Object.values(copy.tickets);
  const saved = savedQ.data ?? copy.saved;
  const attending = [...(upcomingQ.data ?? copy.attending), ...(pastQ.data ?? [])];
  const usingCopy = !ticketsQ.data && copy.syncedAt !== null;
  const loading = enabled && !offline && !ticketsQ.data && !copy.syncedAt && (ticketsQ.isLoading || upcomingQ.isLoading);

  const { upcoming, past } = useMemo(() => {
    const now = Date.now();
    const all = buildVibes(tickets, attending, saved, copy.events);
    const up = all.filter((v) => endTime(v) >= now)
      .sort((a, b) => new Date(a.start ?? 0).getTime() - new Date(b.start ?? 0).getTime());
    // Past: events you had a ticket for or said you were going to.
    const pa = all.filter((v) => endTime(v) < now && (v.tickets.length > 0 || v.going))
      .sort((a, b) => new Date(b.start ?? 0).getTime() - new Date(a.start ?? 0).getTime());
    return { upcoming: up, past: pa };
  }, [tickets, attending, saved, copy.events]);

  if (!user || !token) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4 px-8 text-center">
        <PartyPopper size={48} className="text-primary" aria-hidden />
        <h2 className="text-xl font-black text-text">My Vibes</h2>
        <p className="text-sm text-text-secondary">Log in to see your tickets, plans and the events you&apos;ve been to.</p>
        <Link href="/login"><Button fullWidth>Log In</Button></Link>
      </div>
    );
  }

  const list = tab === "upcoming" ? upcoming : past;
  const setTab = (t: "upcoming" | "past") => router.replace(t === "past" ? "/vibes?tab=past" : "/vibes");

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="My Vibes" />

      {usingCopy && (offline || ticketsQ.isError) && (
        <div role="status" className="flex items-center gap-2 px-4 py-2 bg-bg-elevated border-b border-border text-xs text-text-muted">
          <WifiOff size={12} aria-hidden />
          <span>You&apos;re offline. Showing what&apos;s saved on this phone; tickets open with their QR codes.</span>
        </div>
      )}

      <div role="tablist" aria-label="My Vibes" className="mx-4 mt-3 grid grid-cols-2 p-1 rounded border-2 border-border bg-bg-card">
        {(["upcoming", "past"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={cn("h-9 rounded text-xs font-black uppercase tracking-wide transition-colors",
              tab === t ? "bg-primary text-on-primary" : "text-text-muted hover:text-text")}>
            {t === "upcoming" ? `Upcoming${upcoming.length ? ` · ${upcoming.length}` : ""}` : "Past"}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="px-4 pt-4 space-y-3">
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-28 w-full" />)
        ) : list.length > 0 ? (
          list.map((v) => <VibeCard key={v.eventId} v={v} past={tab === "past"} />)
        ) : (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            <PartyPopper size={40} className="text-border-strong" aria-hidden />
            {tab === "upcoming" ? (
              <>
                <p className="text-text-secondary font-medium">Nothing planned yet</p>
                <p className="text-sm text-text-muted">Tickets, RSVPs and saved events show up here.</p>
                <Link href="/discover"><Button variant="secondary" size="sm">Discover events</Button></Link>
              </>
            ) : (
              <>
                <p className="text-text-secondary font-medium">No past events yet</p>
                <p className="text-sm text-text-muted">
                  {offline ? "Past RSVPs load when you're back online." : "Events you've been to will show up here."}
                </p>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function VibesPage() {
  return <Suspense><MyVibes /></Suspense>;
}
