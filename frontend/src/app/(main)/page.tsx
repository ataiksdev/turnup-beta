"use client";
import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { HeroEvent } from "@/components/events/HeroEvent";
import { EventCarousel } from "@/components/events/EventCarousel";
import { ForYouCard } from "@/components/events/ForYouCard";
import { parsePreferences, displayName as getDisplayName } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";
import Link from "next/link";
import { cn } from "@/lib/utils";
import type { Event } from "@/types";

function getGreeting(name?: string): string {
  const hour = new Date().getHours();
  const part = hour < 12 ? "Morning" : hour < 17 ? "Afternoon" : "Evening";
  return name ? `Good ${part}, ${name.split(" ")[0]}` : `Good ${part}`;
}

function deriveReason(event: Event, prefs: string[]): string | undefined {
  if (!event.category) return undefined;
  if (prefs.includes(event.category.slug)) return `Your ${event.category.name} pick`;
  if (event.is_trending) return "Trending";
  if (event.is_featured) return "Editor's choice";
  return undefined;
}

export default function DiscoverPage() {
  const { token, user } = useAuthStore();
  const prefs = parsePreferences(user?.category_preferences);

  const { data: forYou, isLoading: loadingForYou } = useQuery({
    queryKey: ["events", "for-you", token],
    queryFn: () => eventsApi.forYou(20, token ?? undefined),
  });

  const { data: featured, isLoading: loadingFeatured } = useQuery({
    queryKey: ["events", "featured"],
    queryFn: () => eventsApi.featured(4, token ?? undefined),
  });

  const { data: trending, isLoading: loadingTrending } = useQuery({
    queryKey: ["events", "trending"],
    queryFn: () => eventsApi.trending(10, token ?? undefined),
  });

  const { data: free, isLoading: loadingFree } = useQuery({
    queryKey: ["events", "free"],
    queryFn: () => eventsApi.list({ free: true, limit: 10 }, token ?? undefined),
  });

  const heroEvent = featured?.[0];
  const topPicks = forYou?.slice(0, 3) ?? [];

  return (
    <div className="flex flex-col gap-6 pb-4">
      <TopBar />

      {/* Greeting */}
      <div className="px-4 -mt-2">
        <h1 className="text-2xl font-black text-text">{getGreeting(user ? getDisplayName(user) : undefined)}</h1>
        <p className="text-xs font-bold text-text-muted uppercase tracking-widest mt-1">
          What are you doing this weekend?
        </p>
      </div>

      {/* ── Top Picks / For You — main hero section ── */}
      <section className="px-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xs font-black text-text uppercase tracking-widest">
              {user ? "Top Picks for You" : "Top Picks"}
            </h2>
            {user && prefs.length > 0 && (
              <p className="text-[10px] text-text-muted mt-0.5">
                Personalised · {prefs.slice(0, 2).join(" · ")}
              </p>
            )}
          </div>
          <Link
            href="/search"
            className="text-[10px] font-black text-primary uppercase tracking-widest hover:opacity-80 transition-opacity"
          >
            See all →
          </Link>
        </div>

        {loadingForYou ? (
          <div className="space-y-3">
            <Skeleton className="h-[220px] w-full" />
            <div className="grid grid-cols-2 gap-3">
              <Skeleton className="h-[280px] w-full" />
              <Skeleton className="h-[280px] w-full" />
            </div>
          </div>
        ) : topPicks.length > 0 ? (
          <div className="space-y-3">
            {/* #1 pick — full width */}
            <ForYouCard
              event={topPicks[0]}
              rank={1}
              reason={deriveReason(topPicks[0], prefs)}
            />
            {/* #2 and #3 — side by side */}
            {topPicks.length > 1 && (
              <div className="grid grid-cols-2 gap-3">
                {topPicks.slice(1, 3).map((e, i) => (
                  <ForYouCard
                    key={e.id}
                    event={e}
                    rank={(i + 2) as 2 | 3}
                    reason={deriveReason(e, prefs)}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center h-32 border-2 border-dashed border-border rounded">
            <p className="text-xs text-text-muted font-bold uppercase tracking-wide">
              No picks yet — check back soon
            </p>
          </div>
        )}
      </section>

      {/* Hero featured event — full bleed */}
      {!loadingFeatured && heroEvent && (
        <HeroEvent event={heroEvent} />
      )}

      {/* Trending */}
      <EventCarousel
        title="Trending Now"
        events={trending}
        loading={loadingTrending}
        seeAllHref="/search?trending=true"
      />

      {/* Remaining For You — rest of the personalised list as a carousel */}
      {forYou && forYou.length > 3 && (
        <EventCarousel
          title={user ? "More for You" : "You Might Like"}
          events={forYou.slice(3)}
          loading={false}
        />
      )}

      {/* Free events */}
      <EventCarousel
        title="Free to Attend"
        events={free}
        loading={loadingFree}
        seeAllHref="/search?free=true"
      />
    </div>
  );
}
