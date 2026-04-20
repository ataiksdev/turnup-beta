"use client";
import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Input } from "@/components/ui/Input";
import { EventCard } from "@/components/events/EventCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { Search, X } from "lucide-react";
import { useSearchParams, useRouter } from "next/navigation";
import { useState, Suspense } from "react";
import { cn } from "@/lib/utils";
import Link from "next/link";

const CATEGORIES = [
  { label: "Music",     slug: "music",     emoji: "🎵", color: "bg-[#1a472a]" },
  { label: "Nightlife", slug: "nightlife", emoji: "🌙", color: "bg-[#2d1b69]" },
  { label: "Arts",      slug: "arts",      emoji: "🎨", color: "bg-[#6b2d2d]" },
  { label: "Food",      slug: "food",      emoji: "🍕", color: "bg-[#6b4c1a]" },
  { label: "Tech",      slug: "tech",      emoji: "💻", color: "bg-[#0d3b59]" },
  { label: "Sports",    slug: "sports",    emoji: "⚽", color: "bg-[#1a5c2d]" },
  { label: "Comedy",    slug: "comedy",    emoji: "😂", color: "bg-[#5c3d1a]" },
  { label: "Wellness",  slug: "wellness",  emoji: "🧘", color: "bg-[#2d4a1a]" },
];

function SearchContent() {
  const { token } = useAuthStore();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [activeCategory, setActiveCategory] = useState(searchParams.get("category") ?? "");
  const [freeOnly, setFreeOnly] = useState(searchParams.get("free") === "true");

  const isSearching = q.trim().length > 0 || activeCategory || freeOnly;

  const { data: events, isLoading } = useQuery({
    queryKey: ["events", "search", q, activeCategory, freeOnly],
    queryFn: () =>
      eventsApi.list(
        { q: q || undefined, category: activeCategory || undefined, free: freeOnly || undefined, limit: 30 },
        token ?? undefined,
      ),
    staleTime: 30_000,
    enabled: isSearching,
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
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Events, venues, cities..."
          icon={<Search size={16} />}
          iconRight={q ? (
            <button onClick={() => setQ("")}><X size={14} /></button>
          ) : undefined}
        />

        {/* Category filter chips — shown when actively searching */}
        {isSearching && (
          <div className="snap-scroll gap-2">
            {[{ label: "All", slug: "" }, ...CATEGORIES].map(({ label, slug }) => (
              <button
                key={slug}
                onClick={() => applyCategory(slug)}
                className={cn(
                  "shrink-0 px-4 py-2 rounded border-2 text-xs font-bold uppercase tracking-wide transition-all",
                  activeCategory === slug
                    ? "bg-primary text-white border-primary shadow-brutal-sm"
                    : "bg-bg-card text-text-secondary border-border hover:border-primary hover:text-primary",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {isSearching && (
          <button
            onClick={() => setFreeOnly(!freeOnly)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded border-2 text-xs font-bold uppercase tracking-wide transition-all",
              freeOnly
                ? "bg-success/15 text-success border-success/40 shadow-brutal-sm"
                : "bg-bg-card text-text-secondary border-border hover:border-success/40 hover:text-success",
            )}
          >
            🆓 Free only
          </button>
        )}
      </div>

      {/* Browse grid — shown when not searching */}
      {!isSearching && (
        <div className="px-4 space-y-3">
          <h2 className="text-xs font-black text-text uppercase tracking-widest">Browse categories</h2>
          <div className="grid grid-cols-2 gap-3">
            {CATEGORIES.map(({ label, slug, emoji, color }) => (
              <Link
                key={slug}
                href={`/search?category=${slug}`}
                onClick={() => setActiveCategory(slug)}
                className={cn(
                  "relative h-24 rounded border-2 border-border shadow-brutal overflow-hidden",
                  "hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-lg transition-all duration-100",
                  color,
                )}
              >
                <span className="absolute bottom-2 right-3 text-4xl opacity-70">{emoji}</span>
                <span className="absolute top-3 left-3 text-sm font-black text-white uppercase tracking-wide">
                  {label}
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      {isSearching && (
        <div className="px-4">
          {isLoading ? (
            <div className="grid grid-cols-2 gap-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-52 w-full" />
              ))}
            </div>
          ) : events && events.length > 0 ? (
            <>
              <p className="text-xs font-bold text-text-muted uppercase tracking-widest mb-3">
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
              <p className="text-text-secondary font-bold uppercase tracking-wide text-sm">No events found</p>
              <p className="text-xs text-text-muted">Try different keywords or filters</p>
            </div>
          )}
        </div>
      )}
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
