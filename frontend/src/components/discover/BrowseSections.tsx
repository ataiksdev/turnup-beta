"use client";
import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { EventCard } from "@/components/events/EventCard";
import { formatEventDate, formatPrice, cn } from "@/lib/utils";
import {
  MapPin, Flame, Star, ArrowRight, Tag, Clock,
  CalendarDays, Users, Building2, Sparkles,
} from "lucide-react";
import Link from "next/link";
import { routes } from "@/lib/routes";
import { CATEGORIES, CategoryTile } from "@/components/events/CategoryTile";
import { useCardTracking, type CardTracking } from "@/lib/useCardTracking";

// ── Config ────────────────────────────────────────────────────────────────────


// ── Section components ────────────────────────────────────────────────────────

function SectionHeader({ title, href, icon: Icon }: {
  title: string; href?: string; icon?: typeof Flame;
}) {
  return (
    <div className="flex items-center justify-between px-4 mb-3">
      <div className="flex items-center gap-2">
        {Icon && <Icon size={14} className="text-primary" />}
        <h2 className="text-xs font-black text-text uppercase tracking-widest">{title}</h2>
      </div>
      {href && (
        <Link href={href} className="flex items-center gap-1 text-[10px] font-bold text-primary hover:underline">
          See all <ArrowRight size={10} />
        </Link>
      )}
    </div>
  );
}

function HScrollRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="snap-scroll gap-3 px-4 pb-1">
      {children}
    </div>
  );
}

function networkNote(event: any): string | null {
  if (event.following_count > 0) {
    return `${event.following_count} you follow ${event.following_count === 1 ? "is" : "are"} going`;
  }
  if (event.following_hosted) return "Hosted by someone you follow";
  return null;
}

function MiniEventCard({ event, showNetworkNote, tracking }: {
  event: any; showNetworkNote?: boolean; tracking?: CardTracking;
}) {
  const note = showNetworkNote ? networkNote(event) : null;
  const { ref, onClick } = useCardTracking<HTMLAnchorElement>(event, tracking);
  return (
    <Link
      ref={ref}
      onClick={onClick}
      href={routes.event(event.slug)}
      className="shrink-0 w-44 rounded border-2 border-border bg-bg-card overflow-hidden hover:border-primary transition-colors shadow-brutal-sm"
    >
      <div className="relative h-28 bg-bg-elevated">
        {event.cover_image
          ? <img src={event.cover_image} alt="" className="w-full h-full object-cover" />
          : <div className="w-full h-full bg-gradient-to-br from-primary/20 to-bg-elevated" />
        }
        {event.is_free && (
          <span className="absolute top-1.5 left-1.5 px-1.5 py-0.5 bg-success text-white text-[9px] font-black rounded uppercase">
            Free
          </span>
        )}
        {event.is_trending && (
          <span className="absolute top-1.5 right-1.5 px-1.5 py-0.5 bg-primary text-on-primary text-[9px] font-black rounded uppercase flex items-center gap-0.5">
            <Flame size={8} /> Hot
          </span>
        )}
      </div>
      <div className="p-2.5 space-y-1">
        <p className="text-xs font-bold text-text line-clamp-2 leading-snug">{event.title}</p>
        <p className="text-[10px] text-text-muted flex items-center gap-1">
          <CalendarDays size={9} />
          {formatEventDate(event.start_date)}
        </p>
        {note && (
          <p className="text-[10px] text-primary font-bold flex items-center gap-1">
            <Users size={9} />
            {note}
          </p>
        )}
        <p className="text-[10px] font-bold text-primary">
          {formatPrice(event.is_free, event.price_min, event.price_max)}
        </p>
      </div>
    </Link>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

/** What used to be the Explore page: shown on Discover below the search bar until you search
 *  or pick a filter. */
export function BrowseSections() {
  const { token } = useAuthStore();

  const { data: trending } = useQuery({
    queryKey: ["explore-trending"],
    queryFn: () => eventsApi.trending(12),
    staleTime: 60_000,
  });

  const { data: featured } = useQuery({
    queryKey: ["explore-featured"],
    queryFn: () => eventsApi.featured(4, token ?? undefined),
    staleTime: 60_000,
  });

  const { data: following } = useQuery({
    queryKey: ["explore-following"],
    queryFn: () => eventsApi.following(token!, 12),
    enabled: !!token,
    staleTime: 30_000,
  });

  const { data: free } = useQuery({
    queryKey: ["explore-free"],
    queryFn: () => eventsApi.list({ free: true, sort: "popular", limit: 10 }),
    staleTime: 60_000,
  });

  const { data: newest } = useQuery({
    queryKey: ["explore-newest"],
    queryFn: () => eventsApi.list({ sort: "newest", limit: 10 }),
    staleTime: 60_000,
  });

  // Hero = first featured event
  const hero = featured?.[0];

  return (
    <div className="flex flex-col pb-4">
      {/* ── Venues and Turnup+ ──────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-2 mx-4 mt-3">
        <Link href="/venues" className="p-3 rounded border-2 border-border bg-bg-card shadow-brutal-sm hover:border-primary">
          <Building2 size={18} className="text-primary" aria-hidden />
          <p className="text-sm font-black text-text mt-1">Venues</p>
          <p className="text-[11px] text-text-muted">Halls, lounges and spaces to book</p>
        </Link>
        <Link href="/plus" className="p-3 rounded border-2 border-border bg-primary text-on-primary shadow-brutal-sm">
          <Sparkles size={18} aria-hidden />
          <p className="text-sm font-black mt-1">Turnup+</p>
          <p className="text-[11px] opacity-90">Presale, deals, fast lane</p>
        </Link>
      </div>

      {/* ── Hero featured event ─────────────────────────────────────── */}
      {hero && (
        <Link href={routes.event(hero.slug)} className="relative mx-4 mt-3 h-52 rounded border-2 border-border overflow-hidden shadow-brutal block hover:border-primary transition-colors">
          {hero.cover_image
            ? <img src={hero.cover_image} alt={hero.title} className="w-full h-full object-cover" />
            : <div className="w-full h-full bg-gradient-to-br from-primary/30 to-bg-elevated" />
          }
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />
          <div className="absolute bottom-0 left-0 right-0 p-4">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary text-on-primary text-[9px] font-black rounded uppercase mb-1.5">
              <Star size={9} /> Featured
            </span>
            <h2 className="text-base font-black text-white leading-snug line-clamp-2">{hero.title}</h2>
            <p className="text-xs text-white/70 mt-1 flex items-center gap-1.5">
              <CalendarDays size={10} />
              {formatEventDate(hero.start_date)}
              {hero.city && <><MapPin size={10} />{hero.city}</>}
            </p>
          </div>
        </Link>
      )}

      {/* ── Trending Now ─────────────────────────────────────────────── */}
      {(trending?.length ?? 0) > 0 && (
        <section className="mt-5">
          <SectionHeader title="Trending Now" href="/discover?trending=true" icon={Flame} />
          <HScrollRow>
            {trending!.map((e: any, i: number) => <MiniEventCard key={e.id} event={e} tracking={{ surface: "discover_trending", position: i }} />)}
          </HScrollRow>
        </section>
      )}

      {/* ── From your network ────────────────────────────────────────── */}
      {(following?.length ?? 0) > 0 && (
        <section className="mt-5">
          <SectionHeader title="From Your Network" icon={Users} />
          <HScrollRow>
            {following!.map((e: any, i: number) => <MiniEventCard key={e.id} event={e} showNetworkNote tracking={{ surface: "discover_following", position: i }} />)}
          </HScrollRow>
        </section>
      )}

      {/* ── Browse by category ────────────────────────────────────────── */}
      <section className="mt-5">
        <SectionHeader title="Browse by Category" />
        <div className="px-4 grid grid-cols-4 gap-2">
          {CATEGORIES.map((c) => <CategoryTile key={c.slug} category={c} size="sm" />)}
        </div>
      </section>

      {/* ── Free to attend ───────────────────────────────────────────── */}
      {(free?.length ?? 0) > 0 && (
        <section className="mt-5">
          <SectionHeader title="Free to Attend" href="/discover?free=true" icon={Tag} />
          <HScrollRow>
            {free!.map((e: any, i: number) => <MiniEventCard key={e.id} event={e} tracking={{ surface: "discover_free", position: i }} />)}
          </HScrollRow>
        </section>
      )}

      {/* ── Just added ───────────────────────────────────────────────── */}
      {(newest?.length ?? 0) > 0 && (
        <section className="mt-5">
          <SectionHeader title="Just Added" href="/discover?sort=newest" icon={Clock} />
          <HScrollRow>
            {newest!.map((e: any, i: number) => <MiniEventCard key={e.id} event={e} tracking={{ surface: "discover_new", position: i }} />)}
          </HScrollRow>
        </section>
      )}

      {/* ── Date-based shortcuts ─────────────────────────────────────── */}
      <section className="mt-5 px-4 space-y-2">
        <SectionHeader title="Browse by Date" />
        <div className="grid grid-cols-2 gap-2">
          {[
            { label: "Today",        date: "today",   icon: CalendarDays },
            { label: "This Weekend", date: "weekend", icon: CalendarDays },
            { label: "This Week",    date: "week",    icon: CalendarDays },
            { label: "This Month",   date: "month",   icon: CalendarDays },
          ].map(({ label, date, icon: Icon }) => (
            <Link
              key={date}
              href={`/discover?date=${date}`}
              className="flex items-center gap-2 p-3 rounded border-2 border-border bg-bg-card hover:border-primary hover:text-primary transition-colors"
            >
              <Icon size={14} className="text-text-muted shrink-0" />
              <span className="text-xs font-bold text-text">{label}</span>
              <ArrowRight size={12} className="ml-auto text-text-muted" />
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
