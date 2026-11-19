"use client";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { SlidersHorizontal, Store } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { PlacePicker, type Place } from "@/components/venues/PlacePicker";
import { VenueCard } from "@/components/venues/VenueCard";
import { VENUE_TYPES, venuesApi, type VenueSearch } from "@/lib/marketplace";
import { publicOrigin, STATIC_EXPORT } from "@/lib/routes";
import { useAuthStore } from "@/store/auth";
import { cn } from "@/lib/utils";

const PAGE = 20;

function guessState(city?: string | null): string {
  const c = (city ?? "").toLowerCase();
  if (c.includes("abuja") || c.includes("fct")) return "FCT";
  if (c.includes("port harcourt")) return "Rivers";
  if (c.includes("ibadan")) return "Oyo";
  return "Lagos";
}

export default function VenuesPage() {
  const { user } = useAuthStore();
  const [place, setPlace] = useState<Place>({ state: "Lagos", areaIds: [], near: null });
  useEffect(() => { if (user?.city) setPlace((p) => ({ ...p, state: guessState(user.city) })); }, [user?.city]);
  const [type, setType] = useState("");
  const [capacity, setCapacity] = useState("");
  const [date, setDate] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [sort, setSort] = useState("recommended");

  const params: VenueSearch = {
    state: place.state,
    area_ids: place.areaIds.join(",") || undefined,
    lat: place.near?.lat, lng: place.near?.lng, radius_km: place.near?.radiusKm,
    type: type || undefined,
    min_capacity: capacity ? Number(capacity) : undefined,
    date: date || undefined,
    max_price_kobo: maxPrice ? Number(maxPrice) * 100 : undefined,
    verified_only: verifiedOnly || undefined,
    sort: place.near && sort === "recommended" ? "recommended" : sort,
  };

  const featured = useQuery({ queryKey: ["venues", "featured", params], queryFn: () => venuesApi.featured(params) });
  const results = useInfiniteQuery({
    queryKey: ["venues", "search", params],
    queryFn: ({ pageParam }) => venuesApi.search({ ...params, limit: PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => (pages.length * PAGE < last.total ? pages.length * PAGE : undefined),
  });
  const items = results.data?.pages.flatMap((p) => p.items) ?? [];
  const total = results.data?.pages[0]?.total ?? 0;

  return (
    <div className="pb-24">
      <TopBar title="Venues" />
      <div className="px-4 pt-4 space-y-3">
        <PlacePicker value={place} onChange={setPlace} />
        <div className="flex gap-1.5 overflow-x-auto -mx-4 px-4 pb-1">
          {[{ id: "", label: "All" }, ...VENUE_TYPES].map((t) => (
            <button key={t.id} onClick={() => setType(t.id)}
              className={cn("shrink-0 px-2.5 py-1 rounded border-2 text-xs font-bold",
                type === t.id ? "bg-text text-bg border-border" : "border-border-subtle text-text-secondary")}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowFilters((s) => !s)} aria-expanded={showFilters}
            className="flex items-center gap-1.5 text-xs font-bold text-text border-2 border-border rounded px-2.5 py-1.5">
            <SlidersHorizontal size={13} aria-hidden /> Filters
          </button>
          <select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value)}
            className="h-8 rounded border-2 border-border bg-bg-card px-2 text-xs font-bold text-text">
            <option value="recommended">Recommended</option>
            <option value="rating">Top rated</option>
            {place.near && <option value="distance">Nearest</option>}
            <option value="price">Lowest price</option>
            <option value="newest">Newest</option>
          </select>
          <span className="ml-auto text-[11px] text-text-muted font-bold">{total} venues</span>
        </div>
        {showFilters && (
          <div className="grid grid-cols-2 gap-2 p-3 rounded border-2 border-border bg-bg-card">
            <label className="text-[11px] font-bold text-text-secondary uppercase space-y-1">
              Guests
              <input type="number" min={1} value={capacity} onChange={(e) => setCapacity(e.target.value)}
                className="w-full h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text normal-case" />
            </label>
            <label className="text-[11px] font-bold text-text-secondary uppercase space-y-1">
              Free on
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                className="w-full h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text normal-case" />
            </label>
            <label className="text-[11px] font-bold text-text-secondary uppercase space-y-1">
              Max price (₦)
              <input type="number" min={0} value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)}
                className="w-full h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text normal-case" />
            </label>
            <label className="flex items-center gap-2 text-xs font-bold text-text self-end h-9">
              <input type="checkbox" checked={verifiedOnly} onChange={(e) => setVerifiedOnly(e.target.checked)} />
              Visited by Turnup
            </label>
          </div>
        )}
      </div>

      {!!featured.data?.length && (
        <section className="mt-5" aria-label="Featured venues">
          <h2 className="px-4 mb-2 text-xs font-black text-text uppercase tracking-widest">Featured venues</h2>
          <div className="flex gap-3 overflow-x-auto px-4 pb-1">
            {featured.data.map((v) => <VenueCard key={v.id} venue={v} compact />)}
          </div>
        </section>
      )}

      <section className="mt-5 px-4 grid grid-cols-1 sm:grid-cols-2 gap-3" aria-label="Venues">
        {results.isPending && Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-64 rounded border-2 border-border bg-bg-card animate-pulse" />
        ))}
        {items.map((v) => <VenueCard key={v.id} venue={v} />)}
      </section>
      {!results.isPending && !items.length && (
        <p className="px-4 mt-6 text-sm text-text-muted text-center">No venues match yet. Try another area or fewer filters.</p>
      )}
      {results.hasNextPage && (
        <div className="px-4 mt-4">
          <Button variant="secondary" fullWidth loading={results.isFetchingNextPage} onClick={() => results.fetchNextPage()}>
            Show more
          </Button>
        </div>
      )}

      <div className="mx-4 mt-8 p-4 rounded border-2 border-dashed border-border text-center space-y-2">
        <Store size={20} className="mx-auto text-primary" aria-hidden />
        <p className="text-sm font-bold text-text">Own or manage a venue?</p>
        <p className="text-xs text-text-muted">List it on Turnup and get booked by organizers across Nigeria. Listing is managed on the Turnup website.</p>
        {/* The venue portal is web-only: from the app, open it on the website. */}
        {STATIC_EXPORT
          ? <a href={`${publicOrigin()}/venue`} target="_blank" rel="noopener noreferrer"
              className="inline-block text-xs font-black text-primary underline">List your venue</a>
          : <Link href="/venue" className="inline-block text-xs font-black text-primary underline">List your venue</Link>}
      </div>
    </div>
  );
}
