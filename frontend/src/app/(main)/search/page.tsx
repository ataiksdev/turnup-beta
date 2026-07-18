"use client";
import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Input } from "@/components/ui/Input";
import { EventCard } from "@/components/events/EventCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";
import {
  Search, X, Music, Moon, Palette, Utensils, Monitor,
  Trophy, Laugh, Leaf, MapPin, Shuffle, Tag, Hash,
  Calendar, ArrowUpDown, ChevronDown,
} from "lucide-react";
import { useSearchParams, useRouter } from "next/navigation";
import { useState, Suspense, useEffect, useRef } from "react";
import { cn, parsePreferences } from "@/lib/utils";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import type { EventFilters } from "@/types";
import { startOfDay, endOfDay, addDays, nextSaturday, nextSunday, endOfMonth, isSaturday, isSunday } from "date-fns";

// ── Static config ─────────────────────────────────────────────────────────────

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
  { label: "All types", value: "" },
  { label: "In Person", value: "physical", icon: MapPin },
  { label: "Virtual",   value: "virtual",  icon: Monitor },
  { label: "Hybrid",    value: "hybrid",   icon: Shuffle },
];

const SORT_OPTIONS: { label: string; value: string }[] = [
  { label: "Date",       value: "date" },
  { label: "Popular",    value: "popular" },
  { label: "Price ↑",   value: "price_asc" },
  { label: "Price ↓",   value: "price_desc" },
  { label: "Newest",    value: "newest" },
];

// ── Date range helpers ────────────────────────────────────────────────────────

type DateFilter = "today" | "weekend" | "week" | "month" | "";

function dateRange(filter: DateFilter): { from: string; to: string } | null {
  if (!filter) return null;
  const now = new Date();
  if (filter === "today") {
    return { from: startOfDay(now).toISOString(), to: endOfDay(now).toISOString() };
  }
  if (filter === "weekend") {
    const sat = isSaturday(now) ? now : isSunday(now) ? addDays(now, 6) : nextSaturday(now);
    const sun = isSunday(now) ? now : nextSunday(sat);
    return { from: startOfDay(sat).toISOString(), to: endOfDay(sun).toISOString() };
  }
  if (filter === "week") {
    return { from: startOfDay(now).toISOString(), to: endOfDay(addDays(now, 7)).toISOString() };
  }
  if (filter === "month") {
    return { from: startOfDay(now).toISOString(), to: endOfMonth(now).toISOString() };
  }
  return null;
}

const DATE_CHIPS: { label: string; value: DateFilter }[] = [
  { label: "Today",        value: "today" },
  { label: "This Weekend", value: "weekend" },
  { label: "This Week",    value: "week" },
  { label: "This Month",   value: "month" },
];

// ── Filter badge row ──────────────────────────────────────────────────────────

function FilterBadge({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="flex items-center gap-1 pl-2 pr-1 py-0.5 rounded border-2 border-primary/40 bg-primary/10 text-[10px] font-black text-primary uppercase tracking-wide">
      {label}
      <button onClick={onRemove} className="p-0.5 rounded hover:bg-primary/20 transition-colors" aria-label={`Remove ${label} filter`}>
        <X size={10} />
      </button>
    </span>
  );
}

// ── Main content ──────────────────────────────────────────────────────────────

const PAGE_SIZE = 20;

function SearchContent() {
  const { token, user } = useAuthStore();
  const searchParams = useSearchParams();
  const router = useRouter();

  const userTopCat = parsePreferences(user?.category_preferences)[0];

  // ── Filter state ──────────────────────────────────────────────────────────
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [city, setCity] = useState(searchParams.get("city") ?? "");
  const [activeCategory, setActiveCategory] = useState(searchParams.get("category") ?? "");
  const [activeType, setActiveType] = useState(searchParams.get("event_type") ?? "");
  const [freeOnly, setFreeOnly] = useState(searchParams.get("free") === "true");
  const [dateFilter, setDateFilter] = useState<DateFilter>((searchParams.get("date") as DateFilter) ?? "");
  const [sort, setSort] = useState<string>(searchParams.get("sort") ?? "date");
  const [showSortMenu, setShowSortMenu] = useState(false);

  // ── Pagination ────────────────────────────────────────────────────────────
  const [page, setPage] = useState(1);
  const [allEvents, setAllEvents] = useState<any[]>([]);
  const filtersRef = useRef("");

  // Seed tag from URL param (e.g. /search?tag=afrobeats)
  const urlTag = searchParams.get("tag") ?? "";
  useEffect(() => {
    if (urlTag && !q) setQ(`#${urlTag}`);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlTag]);

  // Seed trending/featured flags from URL (home feed deep-links)
  const urlTrending = searchParams.get("trending") === "true";
  const urlFeatured = searchParams.get("featured") === "true";

  const isTagSearch = q.trim().startsWith("#");
  const tagValue = isTagSearch ? q.trim().slice(1).trim() : "";

  const isSearching = !!(q.trim() || activeCategory || freeOnly || activeType || city.trim()
    || dateFilter || urlTrending || urlFeatured || sort !== "date");

  // Build a stable key for filter changes so we can reset page
  const dr = dateRange(dateFilter);
  const filtersKey = JSON.stringify({ q, city, activeCategory, activeType, freeOnly, dateFilter, sort, urlTrending, urlFeatured });

  // Reset to page 1 whenever filters change
  useEffect(() => {
    if (filtersRef.current !== filtersKey) {
      filtersRef.current = filtersKey;
      setPage(1);
      setAllEvents([]);
    }
  }, [filtersKey]);

  const queryFilters: EventFilters = {
    q: (!isTagSearch && q.trim()) ? q.trim() : undefined,
    tag: (isTagSearch && tagValue) ? tagValue : undefined,
    city: city.trim() || undefined,
    category: activeCategory || undefined,
    event_type: (activeType as EventFilters["event_type"]) || undefined,
    free: freeOnly || undefined,
    trending: urlTrending || undefined,
    featured: urlFeatured || undefined,
    date_from: dr?.from,
    date_to: dr?.to,
    sort: sort as EventFilters["sort"],
    page,
    limit: PAGE_SIZE,
  };

  const { data: pageEvents, isLoading, isFetching } = useQuery({
    queryKey: ["events", "search", queryFilters],
    queryFn: () => eventsApi.list(queryFilters, token ?? undefined),
    staleTime: 30_000,
    enabled: isSearching,
  });

  // Accumulate pages
  useEffect(() => {
    if (!pageEvents) return;
    if (page === 1) {
      setAllEvents(pageEvents);
    } else {
      setAllEvents((prev) => [...prev, ...pageEvents]);
    }
  }, [pageEvents, page]);

  const hasMore = (pageEvents?.length ?? 0) === PAGE_SIZE;

  // ── URL sync helpers ──────────────────────────────────────────────────────
  function pushParams(patch: Record<string, string | undefined>) {
    const p = new URLSearchParams(searchParams.toString());
    // Remove trending/featured deep-link params on any user filter change
    p.delete("trending"); p.delete("featured");
    Object.entries(patch).forEach(([k, v]) => {
      if (v) p.set(k, v); else p.delete(k);
    });
    router.replace(`/search?${p}`);
  }

  function clearAll() {
    setQ(""); setCity(""); setActiveCategory(""); setActiveType("");
    setFreeOnly(false); setDateFilter(""); setSort("date");
    router.replace("/search");
  }

  // Active badges
  const activeBadges: { label: string; clear: () => void }[] = [];
  if (urlTrending) activeBadges.push({ label: "Trending", clear: () => pushParams({ trending: undefined }) });
  if (urlFeatured) activeBadges.push({ label: "Featured", clear: () => pushParams({ featured: undefined }) });
  if (activeCategory) {
    const cat = CATEGORIES.find((c) => c.slug === activeCategory);
    activeBadges.push({ label: cat?.label ?? activeCategory, clear: () => { setActiveCategory(""); pushParams({ category: undefined }); } });
  }
  if (activeType) {
    const t = EVENT_TYPES.find((t) => t.value === activeType);
    activeBadges.push({ label: t?.label ?? activeType, clear: () => { setActiveType(""); pushParams({ event_type: undefined }); } });
  }
  if (freeOnly) activeBadges.push({ label: "Free", clear: () => { setFreeOnly(false); pushParams({ free: undefined }); } });
  if (city.trim()) activeBadges.push({ label: city.trim(), clear: () => { setCity(""); pushParams({ city: undefined }); } });
  if (dateFilter) {
    const chip = DATE_CHIPS.find((d) => d.value === dateFilter);
    activeBadges.push({ label: chip?.label ?? dateFilter, clear: () => { setDateFilter(""); pushParams({ date: undefined }); } });
  }
  if (sort !== "date") {
    const s = SORT_OPTIONS.find((o) => o.value === sort);
    activeBadges.push({ label: `Sort: ${s?.label ?? sort}`, clear: () => { setSort("date"); pushParams({ sort: undefined }); } });
  }

  const sortLabel = SORT_OPTIONS.find((o) => o.value === sort)?.label ?? "Date";

  return (
    <div className="flex flex-col gap-0 pb-4">
      <TopBar title="Search" />

      <div className="px-4 pt-3 space-y-3">
        {/* Search bar */}
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={isTagSearch ? `Tag: #${tagValue || "…"}` : "Events, venues, cities, or #tag…"}
          icon={isTagSearch ? <Hash size={16} className="text-primary" /> : <Search size={16} />}
          iconRight={q ? <button onClick={() => setQ("")} aria-label="Clear search"><X size={14} /></button> : undefined}
        />

        {/* City + Sort row */}
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
            <input
              type="text"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              onBlur={() => pushParams({ city: city.trim() || undefined })}
              placeholder="City"
              className="w-full pl-8 pr-3 py-2 bg-bg-card border-2 border-border rounded text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary transition-colors"
            />
          </div>

          {/* Sort dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowSortMenu((v) => !v)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-2 rounded border-2 text-xs font-bold transition-colors whitespace-nowrap",
                sort !== "date" ? "border-primary text-primary bg-primary/10" : "border-border text-text-secondary bg-bg-card hover:border-border-strong",
              )}
            >
              <ArrowUpDown size={12} />
              {sortLabel}
              <ChevronDown size={11} className={cn("transition-transform", showSortMenu && "rotate-180")} />
            </button>
            {showSortMenu && (
              <div className="absolute right-0 top-full mt-1 z-20 bg-bg-card border-2 border-border rounded shadow-brutal-sm min-w-[120px]">
                {SORT_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    onClick={() => { setSort(o.value); setShowSortMenu(false); pushParams({ sort: o.value !== "date" ? o.value : undefined }); }}
                    className={cn(
                      "w-full text-left px-3 py-2 text-xs font-bold transition-colors",
                      sort === o.value ? "text-primary bg-primary/10" : "text-text-secondary hover:bg-bg-elevated",
                    )}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Date quick-chips */}
        <div className="snap-scroll gap-2">
          <span className="flex items-center gap-1 shrink-0 text-[10px] font-black text-text-muted uppercase tracking-widest">
            <Calendar size={11} />
          </span>
          {DATE_CHIPS.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => { const next = dateFilter === value ? "" : value; setDateFilter(next); pushParams({ date: next || undefined }); }}
              className={cn(
                "shrink-0 px-3 py-1.5 rounded border-2 text-xs font-bold uppercase tracking-wide transition-all",
                dateFilter === value
                  ? "bg-primary text-white border-primary shadow-brutal-sm"
                  : "bg-bg-card text-text-secondary border-border hover:border-primary hover:text-primary",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Category chips */}
        <div className="snap-scroll gap-2">
          {[{ label: "All", slug: "" }, ...CATEGORIES].map(({ label, slug }) => (
            <button
              key={slug}
              onClick={() => { setActiveCategory(slug); pushParams({ category: slug || undefined }); }}
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

        {/* Type + Free chips */}
        <div className="flex flex-wrap gap-2">
          {EVENT_TYPES.map(({ label, value, icon: TypeIcon }) => (
            <button
              key={value}
              onClick={() => { setActiveType(value); pushParams({ event_type: value || undefined }); }}
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
            onClick={() => { const next = !freeOnly; setFreeOnly(next); pushParams({ free: next ? "true" : undefined }); }}
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

        {/* Active filter badges */}
        {activeBadges.length > 0 && (
          <div className="flex flex-wrap gap-1.5 items-center">
            {activeBadges.map((b) => (
              <FilterBadge key={b.label} label={b.label} onRemove={b.clear} />
            ))}
            {activeBadges.length > 1 && (
              <button
                onClick={clearAll}
                className="text-[10px] font-bold text-text-muted hover:text-text-secondary transition-colors underline"
              >
                Clear all
              </button>
            )}
          </div>
        )}

        {/* Tag badge */}
        {isTagSearch && tagValue && (
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1 px-2.5 py-1 bg-primary/15 border-2 border-primary/40 rounded text-xs font-black text-primary uppercase tracking-wide">
              <Hash size={11} aria-hidden />
              {tagValue}
            </span>
            <button onClick={() => setQ("")} className="text-[10px] text-text-muted hover:text-text-secondary">
              Clear tag
            </button>
          </div>
        )}

        {/* Tip — only when completely idle */}
        {!q && !isSearching && (
          <p className="text-[10px] text-text-disabled font-medium">
            Tip: type <span className="text-primary font-bold">#afrobeats</span> to search by tag
          </p>
        )}
      </div>

      {/* Browse grid — shown when not searching */}
      {!isSearching && (
        <div className="px-4 pt-4 space-y-3">
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
        <div className="px-4 pt-4" onClick={() => setShowSortMenu(false)}>
          {isLoading && page === 1 ? (
            <div className="grid grid-cols-2 gap-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-52 w-full" />
              ))}
            </div>
          ) : allEvents.length > 0 ? (
            <>
              <p className="text-xs font-bold text-text-muted uppercase tracking-widest mb-3">
                {isTagSearch
                  ? `${allEvents.length} event${allEvents.length !== 1 ? "s" : ""} tagged #${tagValue}`
                  : `${allEvents.length} event${allEvents.length !== 1 ? "s" : ""} found`}
              </p>
              <div className="grid grid-cols-2 gap-3">
                {allEvents.map((e) => (
                  <EventCard key={e.id} event={e} size="sm" className="w-full" />
                ))}
              </div>

              {/* Load more */}
              {hasMore && (
                <div className="pt-4 flex justify-center">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={isFetching && page > 1}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Load more
                  </Button>
                </div>
              )}
            </>
          ) : !isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
              <Search size={40} className="text-border-strong" aria-hidden />
              <p className="text-text-secondary font-bold uppercase tracking-wide text-sm">
                {isTagSearch ? `No events tagged #${tagValue}` : "No events found"}
              </p>
              <p className="text-xs text-text-muted">Try different keywords or filters</p>
              {activeBadges.length > 0 && (
                <Button variant="secondary" size="sm" onClick={clearAll}>Clear filters</Button>
              )}
            </div>
          ) : null}
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
