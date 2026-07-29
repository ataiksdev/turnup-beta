"use client";
import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { EventCard } from "@/components/events/EventCard";
import { formatEventDate, formatPrice, cn } from "@/lib/utils";
import {
  Music, Moon, Palette, Utensils, Monitor, Trophy, Laugh, Leaf,
  MapPin, Flame, Star, ArrowRight, Tag, Clock,
  CalendarDays,
} from "lucide-react";
import Link from "next/link";

// ── Config ────────────────────────────────────────────────────────────────────

const CATEGORIES = [
  { label: "Music",     slug: "music",     icon: Music,    bg: "bg-[#1a472a]", accent: "#22c55e" },
  { label: "Nightlife", slug: "nightlife", icon: Moon,     bg: "bg-[#2d1b69]", accent: "#a78bfa" },
  { label: "Arts",      slug: "arts",      icon: Palette,  bg: "bg-[#6b2d2d]", accent: "#f87171" },
  { label: "Food",      slug: "food",      icon: Utensils, bg: "bg-[#6b4c1a]", accent: "#fb923c" },
  { label: "Tech",      slug: "tech",      icon: Monitor,  bg: "bg-[#0d3b59]", accent: "#38bdf8" },
  { label: "Sports",    slug: "sports",    icon: Trophy,   bg: "bg-[#1a5c2d]", accent: "#4ade80" },
  { label: "Comedy",    slug: "comedy",    icon: Laugh,    bg: "bg-[#5c3d1a]", accent: "#fbbf24" },
  { label: "Wellness",  slug: "wellness",  icon: Leaf,     bg: "bg-[#2d4a1a]", accent: "#86efac" },
];

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

function MiniEventCard({ event }: { event: any }) {
  return (
    <Link
      href={`/events/${event.slug}`}
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
          <span className="absolute top-1.5 right-1.5 px-1.5 py-0.5 bg-primary text-white text-[9px] font-black rounded uppercase flex items-center gap-0.5">
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
        <p className="text-[10px] font-bold text-primary">
          {formatPrice(event.is_free, event.price_min, event.price_max)}
        </p>
      </div>
    </Link>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ExplorePage() {
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
      <TopBar title="Explore" />

      {/* ── Hero featured event ─────────────────────────────────────── */}
      {hero && (
        <Link href={`/events/${hero.slug}`} className="relative mx-4 mt-3 h-52 rounded border-2 border-border overflow-hidden shadow-brutal block hover:border-primary transition-colors">
          {hero.cover_image
            ? <img src={hero.cover_image} alt={hero.title} className="w-full h-full object-cover" />
            : <div className="w-full h-full bg-gradient-to-br from-primary/30 to-bg-elevated" />
          }
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />
          <div className="absolute bottom-0 left-0 right-0 p-4">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary text-white text-[9px] font-black rounded uppercase mb-1.5">
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
          <SectionHeader title="Trending Now" href="/search?trending=true" icon={Flame} />
          <HScrollRow>
            {trending!.map((e: any) => <MiniEventCard key={e.id} event={e} />)}
          </HScrollRow>
        </section>
      )}

      {/* ── Browse by category ────────────────────────────────────────── */}
      <section className="mt-5">
        <SectionHeader title="Browse by Category" />
        <div className="px-4 grid grid-cols-4 gap-2">
          {CATEGORIES.map(({ label, slug, icon: Icon, bg }) => (
            <Link
              key={slug}
              href={`/search?category=${slug}`}
              className={cn(
                "relative flex flex-col items-center justify-center gap-1.5 h-20 rounded border-2 border-border overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-brutal-sm",
                bg,
              )}
            >
              <Icon size={20} className="text-white/80" />
              <span className="text-[9px] font-black text-white uppercase tracking-wide leading-none">{label}</span>
            </Link>
          ))}
        </div>
      </section>

      {/* ── Free to attend ───────────────────────────────────────────── */}
      {(free?.length ?? 0) > 0 && (
        <section className="mt-5">
          <SectionHeader title="Free to Attend" href="/search?free=true" icon={Tag} />
          <HScrollRow>
            {free!.map((e: any) => <MiniEventCard key={e.id} event={e} />)}
          </HScrollRow>
        </section>
      )}

      {/* ── Just added ───────────────────────────────────────────────── */}
      {(newest?.length ?? 0) > 0 && (
        <section className="mt-5">
          <SectionHeader title="Just Added" href="/search?sort=newest" icon={Clock} />
          <HScrollRow>
            {newest!.map((e: any) => <MiniEventCard key={e.id} event={e} />)}
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
              href={`/search?date=${date}`}
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
