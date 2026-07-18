"use client";
import { useQuery } from "@tanstack/react-query";
import { eventsApi, communitiesApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { HeroEvent } from "@/components/events/HeroEvent";
import { EventCarousel } from "@/components/events/EventCarousel";
import { ForYouCard } from "@/components/events/ForYouCard";
import { parsePreferences, displayName as getDisplayName } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Users, Lock, CheckCircle2 } from "lucide-react";
import type { Event, User } from "@/types";

function getGreeting(name?: string): string {
  const hour = new Date().getHours();
  const part = hour < 12 ? "Morning" : hour < 17 ? "Afternoon" : "Evening";
  return name ? `Good ${part}, ${name.split(" ")[0]}` : `Good ${part}`;
}

function getSubtitle(user: User | null): string {
  if (!user) return "What are you doing this weekend?";
  if (user.city && user.goes_out_when === "weekends") return `What's on in ${user.city} this weekend?`;
  if (user.city) return `What's happening in ${user.city}?`;
  if (user.goes_out_when === "weekdays") return "What's on this week?";
  return "What are you doing this weekend?";
}

const CAT_LABELS: Record<string, string> = {
  music: "Music", nightlife: "Nightlife", arts: "Arts", food: "Food & Drink",
  tech: "Tech", sports: "Sports", comedy: "Comedy", wellness: "Wellness",
};

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

  const { data: inCity } = useQuery({
    queryKey: ["events", "city", user?.city],
    queryFn: () => eventsApi.list({ city: user!.city!, limit: 8 }, token ?? undefined),
    enabled: !!user?.city,
  });

  const topCatSlug = prefs[0];
  const { data: byCat } = useQuery({
    queryKey: ["events", "cat", topCatSlug],
    queryFn: () => eventsApi.list({ category: topCatSlug, limit: 8 }, token ?? undefined),
    enabled: !!topCatSlug,
  });

  const { data: myCommunities } = useQuery({
    queryKey: ["communities-my"],
    queryFn: () => communitiesApi.my(token!),
    enabled: !!token,
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
          {getSubtitle(user)}
        </p>
      </div>

      {/* ── Your Communities ── */}
      {myCommunities && myCommunities.length > 0 && (
        <section className="space-y-3">
          <div className="px-4 flex items-center justify-between">
            <h2 className="text-xs font-black text-text uppercase tracking-widest">Your Communities</h2>
            <Link href="/communities" className="text-[10px] font-black text-primary uppercase tracking-widest hover:opacity-80 transition-opacity">
              See all →
            </Link>
          </div>
          <div className="flex gap-3 overflow-x-auto px-4 pb-1 snap-x snap-mandatory no-scrollbar">
            {myCommunities.slice(0, 10).map((c: any) => (
              <Link
                key={c.id}
                href={`/communities/${c.slug}`}
                className="snap-start shrink-0 w-32 flex flex-col items-center gap-2 p-3 rounded border-2 border-border bg-bg-card hover:border-primary transition-colors text-center"
              >
                <div className="w-12 h-12 rounded-full bg-bg-elevated flex items-center justify-center overflow-hidden relative">
                  {c.cover_image ? (
                    <img src={c.cover_image} alt="" className="w-full h-full object-cover" />
                  ) : c.icon ? (
                    <span className="text-2xl">{c.icon}</span>
                  ) : (
                    <Users size={20} className="text-text-muted" />
                  )}
                  {c.is_verified_community && (
                    <CheckCircle2 size={12} className="absolute bottom-0 right-0 text-primary fill-bg-card" />
                  )}
                </div>
                <div className="min-w-0 w-full">
                  <p className="text-[11px] font-bold text-text line-clamp-2 leading-tight">{c.name}</p>
                  <p className="text-[10px] text-text-muted mt-0.5 flex items-center justify-center gap-0.5">
                    {c.is_private && <Lock size={8} />}
                    {c.member_count.toLocaleString()} members
                  </p>
                </div>
              </Link>
            ))}
            <Link
              href="/communities"
              className="snap-start shrink-0 w-20 flex flex-col items-center justify-center gap-1.5 p-3 rounded border-2 border-dashed border-border hover:border-primary transition-colors text-center"
            >
              <Users size={18} className="text-text-muted" />
              <p className="text-[10px] font-bold text-text-muted">Explore</p>
            </Link>
          </div>
        </section>
      )}

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

      {user?.city && inCity && inCity.length > 0 && (
        <EventCarousel
          title={`In ${user.city} This Weekend`}
          events={inCity}
        />
      )}

      {topCatSlug && byCat && byCat.length > 0 && (
        <EventCarousel
          title={`Because You Love ${CAT_LABELS[topCatSlug] ?? topCatSlug}`}
          events={byCat}
        />
      )}

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
