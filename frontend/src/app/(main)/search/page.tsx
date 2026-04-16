"use client";
import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Input } from "@/components/ui/Input";
import { EventCard } from "@/components/events/EventCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { Search, SlidersHorizontal, X } from "lucide-react";
import { useSearchParams, useRouter } from "next/navigation";
import { useState, useCallback, Suspense } from "react";
import { cn } from "@/lib/utils";
import { useQuery as useCategories } from "@tanstack/react-query";

const CATEGORIES = [
  { label: "All",       slug: "" },
  { label: "🎵 Music",   slug: "music" },
  { label: "🌙 Nightlife",slug: "nightlife" },
  { label: "🎨 Arts",    slug: "arts" },
  { label: "🍕 Food",    slug: "food" },
  { label: "💻 Tech",    slug: "tech" },
  { label: "⚽ Sports",  slug: "sports" },
  { label: "😂 Comedy",  slug: "comedy" },
  { label: "🧘 Wellness",slug: "wellness" },
];

function SearchContent() {
  const { token } = useAuthStore();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [activeCategory, setActiveCategory] = useState(searchParams.get("category") ?? "");
  const [freeOnly, setFreeOnly] = useState(searchParams.get("free") === "true");

  const { data: events, isLoading } = useQuery({
    queryKey: ["events", "search", q, activeCategory, freeOnly],
    queryFn: () =>
      eventsApi.list(
        {
          q: q || undefined,
          category: activeCategory || undefined,
          free: freeOnly || undefined,
          limit: 30,
        },
        token ?? undefined,
      ),
    staleTime: 30_000,
  });

  function applyCategory(slug: string) {
    setActiveCategory(slug);
    const params = new URLSearchParams(searchParams.toString());
    if (slug) params.set("category", slug);
    else params.delete("category");
    router.replace(`/search?${params}`);
  }

  return (
    <div className="flex flex-col gap-4 pb-4">
      <TopBar title="Search" />

      <div className="px-4 space-y-3">
        {/* Search input */}
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Events, venues, cities..."
          icon={<Search size={16} />}
          iconRight={q ? (
            <button onClick={() => setQ("")}><X size={14} /></button>
          ) : undefined}
        />

        {/* Filter chips */}
        <div className="snap-scroll gap-2">
          {CATEGORIES.map(({ label, slug }) => (
            <button
              key={slug}
              onClick={() => applyCategory(slug)}
              className={cn(
                "shrink-0 px-4 py-2 rounded-2xl text-sm font-medium transition-all border",
                activeCategory === slug
                  ? "bg-primary text-white border-primary"
                  : "bg-bg-card text-text-secondary border-border hover:border-primary hover:text-primary",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Free toggle */}
        <button
          onClick={() => setFreeOnly(!freeOnly)}
          className={cn(
            "flex items-center gap-2 px-4 py-2 rounded-2xl text-sm font-medium transition-all border",
            freeOnly
              ? "bg-success/15 text-success border-success/40"
              : "bg-bg-card text-text-secondary border-border",
          )}
        >
          🆓 Free events only
        </button>
      </div>

      {/* Results */}
      <div className="px-4">
        {isLoading ? (
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-52 w-full" />
            ))}
          </div>
        ) : events && events.length > 0 ? (
          <>
            <p className="text-xs text-text-muted mb-3">
              {events.length} event{events.length !== 1 ? "s" : ""} found
            </p>
            <div className="grid grid-cols-2 gap-3">
              {events.map((e) => (
                <EventCard key={e.id} event={e} size="sm" className="w-full" />
              ))}
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
            <span className="text-5xl">🔍</span>
            <p className="text-text-secondary font-medium">No events found</p>
            <p className="text-sm text-text-muted">Try different keywords or filters</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense>
      <SearchContent />
    </Suspense>
  );
}
