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
        <h1 className="text-2xl font-black text-text">
          {user ? `Hey, ${user.full_name.split(" ")[0]} 👋` : "Discover Events"}
        </h1>
        <p className="text-sm text-text-muted mt-0.5">
          What are you doing this weekend?
        </p>
      </div>

      {/* Category quick filters */}
      <div className="snap-scroll px-4 gap-2">
        {[
          { label: "All", slug: "" },
          { label: "🎵 Music", slug: "music" },
          { label: "🌙 Nightlife", slug: "nightlife" },
          { label: "🎨 Arts", slug: "arts" },
          { label: "🍕 Food", slug: "food" },
          { label: "💻 Tech", slug: "tech" },
          { label: "⚽ Sports", slug: "sports" },
          { label: "😂 Comedy", slug: "comedy" },
          { label: "🧘 Wellness", slug: "wellness" },
        ].map(({ label, slug }) => (
          <Link
            key={slug}
            href={slug ? `/search?category=${slug}` : "/search"}
            className="shrink-0 px-4 py-2 rounded-2xl bg-bg-card border border-border text-sm font-medium text-text-secondary hover:border-primary hover:text-primary transition-colors"
          >
            {label}
          </Link>
        ))}
      </div>

      {/* Hero event */}
      {loadingFeatured ? (
        <div className="mx-4 h-[420px] rounded-3xl">
          <Skeleton className="h-full w-full rounded-3xl" />
        </div>
      ) : heroEvent ? (
        <HeroEvent event={heroEvent} />
      ) : null}

      {/* Trending */}
      <EventCarousel
        title="🔥 Trending Now"
        events={trending}
        loading={loadingTrending}
        seeAllHref="/search?trending=true"
      />

      {/* For You (based on preferences) */}
      {user && (
        <EventCarousel
          title={prefs.length > 0 ? `✨ Based on your taste` : "✨ Picked for You"}
          events={forYou}
          loading={loadingForYou}
        />
      )}

      {/* Free events */}
      <EventCarousel
        title="🆓 Free to Attend"
        events={free}
        loading={loadingFree}
        seeAllHref="/search?free=true"
      />

      {/* Featured grid */}
      {featured && featured.length > 1 && (
        <section className="space-y-3 px-4">
          <h2 className="text-base font-bold text-text">⭐ Featured</h2>
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
