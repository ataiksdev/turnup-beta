"use client";
import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { ForYouCard } from "@/components/events/ForYouCard";
import { EventCard } from "@/components/events/EventCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";
import { parsePreferences } from "@/lib/utils";
import { Sparkles, MapPin, Tag, Clock, Lock } from "lucide-react";
import Link from "next/link";
import type { Event } from "@/types";

const CAT_LABELS: Record<string, string> = {
  music: "Music", nightlife: "Nightlife", arts: "Arts", food: "Food & Drink",
  tech: "Tech", sports: "Sports", comedy: "Comedy", wellness: "Wellness",
};

function deriveReason(event: Event, prefs: string[]): string | undefined {
  if (event.category && prefs.includes(event.category.slug))
    return `Your ${event.category.name} pick`;
  if (event.is_trending) return "Trending";
  if (event.is_featured) return "Editor's pick";
  return undefined;
}

export default function ForYouPage() {
  const { token, user } = useAuthStore();
  const prefs = parsePreferences(user?.category_preferences);

  const { data: events, isLoading } = useQuery({
    queryKey: ["events", "for-you-full", token],
    queryFn: () => eventsApi.forYou(50, token ?? undefined),
    staleTime: 60_000,
  });

  if (!user || !token) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4 px-8 text-center">
        <Lock size={48} className="text-primary" />
        <p className="text-sm font-bold text-text-secondary">Sign in to see your personalised feed</p>
        <Link href="/login"><Button>Log In</Button></Link>
      </div>
    );
  }

  // Personalisation summary chips
  const signals: { icon: typeof MapPin; label: string }[] = [];
  if (user.city) signals.push({ icon: MapPin, label: user.city });
  prefs.slice(0, 3).forEach((p) => signals.push({ icon: Tag, label: CAT_LABELS[p] ?? p }));
  if (user.goes_out_when && user.goes_out_when !== "any")
    signals.push({ icon: Clock, label: user.goes_out_when === "weekends" ? "Weekends" : "Weekdays" });

  const topThree = events?.slice(0, 3) ?? [];
  const rest = events?.slice(3) ?? [];

  return (
    <div className="flex flex-col pb-8">
      <TopBar back title="For You" />

      {/* Personalisation header */}
      <div className="px-4 pt-4 pb-3 space-y-2">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-primary" />
          <p className="text-[10px] font-black text-text-muted uppercase tracking-widest">
            Personalised picks
          </p>
        </div>
        {signals.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {signals.map(({ icon: Icon, label }) => (
              <span
                key={label}
                className="flex items-center gap-1 px-2 py-0.5 rounded border border-border bg-bg-card text-[10px] font-bold text-text-secondary"
              >
                <Icon size={9} className="text-primary" />
                {label}
              </span>
            ))}
            <Link
              href="/onboarding"
              className="flex items-center gap-1 px-2 py-0.5 rounded border border-primary/30 bg-primary/10 text-[10px] font-bold text-primary"
            >
              Edit preferences →
            </Link>
          </div>
        ) : (
          <p className="text-xs text-text-muted">
            <Link href="/onboarding" className="text-primary font-bold hover:underline">Complete your preferences</Link>
            {" "}to get better picks.
          </p>
        )}
      </div>

      {/* Content */}
      <div className="px-4 space-y-4">
        {isLoading ? (
          <>
            <Skeleton className="h-[220px] w-full" />
            <div className="grid grid-cols-2 gap-3">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-52" />)}
            </div>
          </>
        ) : events && events.length > 0 ? (
          <>
            {/* Top 3 — ForYouCard layout (matching home) */}
            {topThree.length > 0 && (
              <div className="space-y-3">
                <ForYouCard
                  event={topThree[0]}
                  rank={1}
                  reason={deriveReason(topThree[0], prefs)}
                />
                {topThree.length > 1 && (
                  <div className="grid grid-cols-2 gap-3">
                    {topThree.slice(1).map((e, i) => (
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
            )}

            {/* Rest — compact EventCard grid */}
            {rest.length > 0 && (
              <>
                <div className="flex items-center gap-2 pt-2">
                  <div className="flex-1 h-px bg-border" />
                  <p className="text-[10px] font-black text-text-muted uppercase tracking-widest shrink-0">
                    More picks · {rest.length}
                  </p>
                  <div className="flex-1 h-px bg-border" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  {rest.map((e) => (
                    <EventCard key={e.id} event={e} size="sm" className="w-full" />
                  ))}
                </div>
              </>
            )}

            <p className="text-[10px] text-text-disabled text-center pt-2">
              Showing {events.length} personalised pick{events.length !== 1 ? "s" : ""}
            </p>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
            <Sparkles size={40} className="text-border-strong" />
            <p className="text-sm font-black text-text-secondary uppercase tracking-wide">No picks yet</p>
            <p className="text-xs text-text-muted">
              Set your city and interests so we can find events for you.
            </p>
            <Link href="/onboarding"><Button size="sm" variant="secondary">Set preferences</Button></Link>
          </div>
        )}
      </div>
    </div>
  );
}
