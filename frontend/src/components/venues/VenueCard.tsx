"use client";
import Link from "next/link";
import { BadgeCheck, MapPin, Star, Users } from "lucide-react";
import { routes } from "@/lib/routes";
import { priceLabel, VENUE_TYPES, type VenueCard as Venue } from "@/lib/marketplace";
import { cn } from "@/lib/utils";

export function VenueCard({ venue, compact }: { venue: Venue; compact?: boolean }) {
  const type = VENUE_TYPES.find((t) => t.id === venue.type)?.label;
  return (
    <Link
      href={routes.venue(venue.slug)}
      className={cn(
        "block rounded border-2 border-border bg-bg-card overflow-hidden shadow-brutal-sm hover:border-primary transition-colors",
        compact && "shrink-0 w-60",
      )}
    >
      <div className={cn("relative bg-bg-elevated", compact ? "h-32" : "h-40")}>
        {venue.cover_image
          ? <img src={venue.cover_image} alt="" className="w-full h-full object-cover" />
          : <div className="w-full h-full bg-gradient-to-br from-primary/25 to-bg-elevated" />}
        <div className="absolute top-2 left-2 flex gap-1">
          {venue.featured && (
            <span className="px-1.5 py-0.5 rounded bg-primary text-on-primary text-[10px] font-black uppercase">Featured</span>
          )}
          {venue.is_pro && (
            <span className="px-1.5 py-0.5 rounded bg-bg-card text-text text-[10px] font-black uppercase border border-border">Pro</span>
          )}
        </div>
      </div>
      <div className="p-3 space-y-1">
        <div className="flex items-center gap-1">
          <h3 className="text-sm font-black text-text truncate">{venue.name}</h3>
          {venue.is_verified && <BadgeCheck size={14} className="text-primary shrink-0" aria-label="Verified by Turnup" />}
        </div>
        <p className="text-[11px] text-text-muted flex items-center gap-1 truncate">
          <MapPin size={11} aria-hidden /> {[venue.area, venue.state === "FCT" ? "Abuja" : venue.state].filter(Boolean).join(", ")}
          {venue.distance_m != null && <span> · {(venue.distance_m / 1000).toFixed(1)} km</span>}
        </p>
        <div className="flex items-center justify-between gap-2 text-[11px] text-text-secondary">
          <span className="flex items-center gap-1"><Users size={11} aria-hidden /> Up to {venue.capacity.toLocaleString()}</span>
          {venue.rating_organizers != null && (
            <span className="flex items-center gap-0.5"><Star size={11} className="text-warning" aria-hidden />
              {venue.rating_organizers.toFixed(1)}</span>
          )}
        </div>
        <p className="text-xs font-bold text-text">{priceLabel(venue.price)}</p>
        {!compact && type && <p className="text-[10px] uppercase tracking-wide font-bold text-text-muted">{type}</p>}
      </div>
    </Link>
  );
}
