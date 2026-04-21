"use client";
import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Input } from "@/components/ui/Input";
import { EventCard } from "@/components/events/EventCard";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  Search, X, Music, Moon, Palette, Utensils, Monitor,
  Trophy, Laugh, Leaf, MapPin, Shuffle, Tag, Hash,
} from "lucide-react";
import { useSearchParams, useRouter } from "next/navigation";
import { useState, Suspense, useEffect } from "react";
import { cn } from "@/lib/utils";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";

const CATEGORIES: { label: string; slug: string; icon: LucideIcon; color: string }[] = [
  { label: "Music",     slug: "music",     icon: Music,    color: "bg-[#1a472a]" },
  { label: "Nightlife", slug: "nightlife", icon: Moon,     color: "bg-[#2d1b69]" },
  { label: "Arts",      slug: "arts",      icon: Palette,  color: "bg-[#6b2d2d]" },
  { label: "Food",      slug: "food",      icon: Utensils, color: "bg-[#6b4c1a]" },
  { label: "Tech",      slug: "tech",      icon: Monitor,  color: "bg-[#0d3b59]" },
  { label: "Sports",    slug: "sports",    icon: Trophy,   color: "bg-[#1a5c2d]" },
  { label: "Comedy",    slug: "comedy",    icon: Laugh,    color: "bg-[#5c3d1a]" },
  { label: "Wellness",  slug: "wellness",  icon: Leaf,     color: "bg-[#2d4a1a]" },
];

const EVENT_TYPES: { label: string; value: string; icon?: LucideIcon }[] = [
  { label: "All Types", value: "" },
  { label: "In Person", value: "physical", icon: MapPin },
  { label: "Virtual",   value: "virtual",  icon: Monitor },
  { label: "Hybrid",    value: "hybrid",   icon: Shuffle },
];

function SearchContent() {
  const { token } = useAuthStore();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [activeCategory, setActiveCategory] = useState(searchParams.get("category") ?? "");
  const [activeType, setActiveType] = useState(searchParams.get("event_type") ?? "");
  const [freeOnly, setFreeOnly] = useState(searchParams.get("free") === "true");

  // Seed tag from URL param (e.g. from ForYouCard tag click → /search?tag=afrobeats)
  const urlTag = searchParams.get("tag") ?? "";
  useEffect(() => {
    if (urlTag && !q) setQ(`#${urlTag}`);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlTag]);

  // Detect tag search: input starting with #
  const isTagSearch = q.trim().startsWith("#");
  const tagValue = isTagSearch ? q.trim().slice(1).trim() : "";

  const isSearching = q.trim().length > 0 || !!activeCategory || freeOnly || !!activeType;

  const { data: events, isLoading } = useQuery({
    queryKey: ["events", "search", q, activeCategory, activeType, freeOnly],
    queryFn: () =>
      eventsApi.list(
        {
          q: (!isTagSearch && q) ? q : undefined,
          tag: (isTagSearch && tagValue) ? tagValue : undefined,
          category: activeCategory || undefined,
          event_type: (activeType as "physical" | "virtual" | "hybrid") || undefined,
          free: freeOnly || undefined,
          limit: 30,
        },
        token ?? undefined,
      ),
    staleTime: 30_000,
    enabled: isSearching,
  });

  function applyCategory(slug: string) {
    setActiveCategory(slug);
    const params = new URLSearchParams(searchParams.toString());
    if (slug) params.set("category", slug); else params.delete("category");
    router.replace(`/search?${params}`);
  }

  function applyType(value: string) {
    setActiveType(value);
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set("event_type", value); else params.delete("event_type");
    router.replace(`/search?${params}`);
  }

  const placeholder = isTagSearch
    ? `Tag: #${tagValue || "…"}`
    : "Events, venues, cities, or #tag…";

  return (
    <div className="flex flex-col gap-4 pb-4">
      <TopBar title="Search" />

      <div className="px-4 space-y-3">
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={placeholder}
          icon={isTagSearch ? <Hash size={16} className="text-primary" /> : <Search size={16} />}
          iconRight={q ? (
            <button onClick={() => setQ("")}><X size={14} /></button>
          ) : undefined}
        />

        {/* Tag search hint */}
        {!q && (
          <p className="text-[10px] text-text-disabled font-medium">
            Tip: type <span className="text-primary font-bold">#afrobeats</span> to search by tag
          </p>
        )}

        {/* Active tag badge */}
        {isTagSearch && tagValue && (
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1 px-2.5 py-1 bg-primary/15 border-2 border-primary/40 rounded text-xs font-black text-primary uppercase tracking-wide">
              <Hash size={11} aria-hidden />
              {tagValue}
            </span>
            <button
              onClick={() => setQ("")}
              className="text-[10px] text-text-muted hover:text-text-secondary"
            >
              Clear tag
            </button>
          </div>
        )}

        {/* Category filter chips */}
        {isSearching && !isTagSearch && (
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

        {/* Event type + free chips */}
        {isSearching && !isTagSearch && (
          <div className="flex flex-wrap gap-2">
            {EVENT_TYPES.map(({ label, value, icon: TypeIcon }) => (
              <button
                key={value}
                onClick={() => applyType(value)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded border-2 text-xs font-bold uppercase tracking-wide transition-all",
                  activeType === value
                    ? "bg-primary text-white border-primary shadow-brutal-sm"
                    : "bg-bg-card text-text-secondary border-border hover:border-primary hover:text-primary",
                )}
              >
                {TypeIcon && <TypeIcon size={11} aria-hidden />}
                {label}
              </button>
            ))}
            <button
              onClick={() => setFreeOnly(!freeOnly)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded border-2 text-xs font-bold uppercase tracking-wide transition-all",
                freeOnly
                  ? "bg-success/15 text-success border-success/40 shadow-brutal-sm"
                  : "bg-bg-card text-text-secondary border-border hover:border-success/40 hover:text-success",
              )}
            >
              <Tag size={11} aria-hidden /> Free only
            </button>
          </div>
        )}
      </div>

      {/* Browse grid — shown when not searching */}
      {!isSearching && (
        <div className="px-4 space-y-3">
          <h2 className="text-xs font-black text-text uppercase tracking-widest">Browse categories</h2>
          <div className="grid grid-cols-2 gap-3">
            {CATEGORIES.map(({ label, slug, icon: CatIcon, color }) => (
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
                <CatIcon size={36} className="absolute bottom-2 right-3 text-white opacity-60" aria-hidden />
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
                {isTagSearch
                  ? `${events.length} event${events.length !== 1 ? "s" : ""} tagged #${tagValue}`
                  : `${events.length} event${events.length !== 1 ? "s" : ""} found`}
              </p>
              <div className="grid grid-cols-2 gap-3">
                {events.map((e) => (
                  <EventCard key={e.id} event={e} size="sm" className="w-full" />
                ))}
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
              <Search size={40} className="text-border-strong" aria-hidden />
              <p className="text-text-secondary font-bold uppercase tracking-wide text-sm">
                {isTagSearch ? `No events tagged #${tagValue}` : "No events found"}
              </p>
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
