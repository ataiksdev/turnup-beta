"use client";
import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { HeroEvent } from "@/components/events/HeroEvent";
import { EventCarousel } from "@/components/events/EventCarousel";
import { EventCard } from "@/components/events/EventCard";
import { parsePreferences } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Music, Moon, Palette, Utensils, Monitor, Trophy, Laugh, Leaf } from "lucide-react";
import type { LucideIcon } from "lucide-react";

function getGreeting(name?: string): string {
  const hour = new Date().getHours();
  const part = hour < 12 ? "Morning" : hour < 17 ? "Afternoon" : "Evening";
  return name ? `Good ${part}, ${name.split(" ")[0]}` : `Good ${part}`;
}

const CATEGORY_TILES: { label: string; slug: string; icon: LucideIcon; color: string }[] = [
  { label: "Music",     slug: "music",     icon: Music,   color: "bg-[#1a472a]" },
  { label: "Nightlife", slug: "nightlife", icon: Moon,    color: "bg-[#2d1b69]" },
  { label: "Arts",      slug: "arts",      icon: Palette, color: "bg-[#6b2d2d]" },
  { label: "Food",      slug: "food",      icon: Utensils, color: "bg-[#6b4c1a]" },
  { label: "Tech",      slug: "tech",      icon: Monitor, color: "bg-[#0d3b59]" },
  { label: "Sports",    slug: "sports",    icon: Trophy,  color: "bg-[#1a5c2d]" },
  { label: "Comedy",    slug: "comedy",    icon: Laugh,   color: "bg-[#5c3d1a]" },
  { label: "Wellness",  slug: "wellness",  icon: Leaf,    color: "bg-[#2d4a1a]" },
];

export default function DiscoverPage() {
  const { token, user } = useAuthStore();
  const prefs = parsePreferences(user?.category_preferences);

  const { data: featured, isLoading: loadingFeatured } = useQuery({
    queryKey: ["events", "featured"],
    queryFn: () => eventsApi.featured(4, token ?? undefined),
  });

  const { data: trending, isLoading: loadingTrending } = useQuery({
    queryKey: ["events", "trending"],
    queryFn: () => eventsApi.trending(10, token ?? undefined),
  });

  const { data: forYou, isLoading: loadingForYou } = useQuery({
    queryKey: ["events", "for-you", prefs.join(",")],
    queryFn: () =>
      prefs.length > 0
        ? eventsApi.list({ category: prefs[0], limit: 10 }, token ?? undefined)
        : eventsApi.list({ limit: 10 }, token ?? undefined),
    enabled: true,
  });

  const { data: free, isLoading: loadingFree } = useQuery({
    queryKey: ["events", "free"],
    queryFn: () => eventsApi.list({ free: true, limit: 10 }, token ?? undefined),
  });

  const heroEvent = featured?.[0];

  return (
    <div className="flex flex-col gap-6 pb-4">
      <TopBar />

      {/* Greeting */}
      <div className="px-4 -mt-2">
        <h1 className="text-2xl font-black text-text">{getGreeting(user?.full_name)}</h1>
        <p className="text-xs font-bold text-text-muted uppercase tracking-widest mt-1">
          What are you doing this weekend?
        </p>
      </div>

      {/* Hero event — full bleed */}
      {loadingFeatured ? (
        <Skeleton className="h-[500px] w-full rounded-none" />
      ) : heroEvent ? (
        <HeroEvent event={heroEvent} />
      ) : null}

      {/* Trending */}
      <EventCarousel
        title="Trending Now"
        events={trending}
        loading={loadingTrending}
        seeAllHref="/search?trending=true"
      />

      {/* Browse categories */}
      <section className="space-y-3">
        <div className="flex items-center justify-between px-4">
          <h2 className="text-xs font-black text-text uppercase tracking-widest">Browse</h2>
          <Link href="/search" className="text-[10px] font-black text-primary uppercase tracking-widest">
            All categories
          </Link>
        </div>
        <div className="grid grid-cols-2 gap-3 px-4">
          {CATEGORY_TILES.map(({ label, slug, icon: Icon, color }) => (
            <Link
              key={slug}
              href={`/search?category=${slug}`}
              className={cn(
                "relative h-20 rounded border-2 border-border shadow-brutal overflow-hidden",
                "hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-lg transition-all duration-100",
                color,
              )}
            >
              <Icon size={32} className="absolute bottom-2 right-3 text-white opacity-60" aria-hidden />
              <span className="absolute top-3 left-3 text-sm font-black text-white uppercase tracking-wide">
                {label}
              </span>
            </Link>
          ))}
        </div>
      </section>

      {/* For You */}
      {user && (
        <EventCarousel
          title={prefs.length > 0 ? "Based on Your Taste" : "Picked for You"}
          events={forYou}
          loading={loadingForYou}
        />
      )}

      {/* Free events */}
      <EventCarousel
        title="Free to Attend"
        events={free}
        loading={loadingFree}
        seeAllHref="/search?free=true"
      />

      {/* Featured grid */}
      {featured && featured.length > 1 && (
        <section className="space-y-3 px-4">
          <h2 className="text-xs font-black text-text uppercase tracking-widest">Featured</h2>
          <div className="grid grid-cols-2 gap-3">
            {featured.slice(1).map((e) => (
              <EventCard key={e.id} event={e} size="sm" className="w-full" />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
