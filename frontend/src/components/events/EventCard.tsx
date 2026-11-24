"use client";
import { cn, formatEventDateShort, formatPrice } from "@/lib/utils";
import type { Event } from "@/types";
import { AlertCircle, Bookmark, BookmarkCheck, Flame } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { routes } from "@/lib/routes";
import { useOfflineImage } from "@/lib/offlineImages";
import { useCardTracking, type CardTracking } from "@/lib/useCardTracking";

interface EventCardProps {
  event: Event;
  size?: "sm" | "md" | "lg";
  className?: string;
  /** Where it's shown, for impression and click tracking (lib/useCardTracking.ts). */
  tracking?: CardTracking;
}

export function EventCard({ event, size = "md", className, tracking }: EventCardProps) {
  const { ref, onClick } = useCardTracking<HTMLAnchorElement>(event, tracking);
  const coverSrc = useOfflineImage(event.cover_image); // kept copy while offline
  const { token } = useAuthStore();
  const [saved, setSaved] = useState(event.is_saved);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);

  async function toggleSave(e: React.MouseEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setSaving(true);
    setSaveError(false);
    try {
      const res = await eventsApi.save(token, event.id);
      setSaved(res.saved);
    } catch {
      setSaveError(true);
      setTimeout(() => setSaveError(false), 2500);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Link
      ref={ref}
      onClick={onClick}
      href={routes.event(event.slug)}
      className={cn(
        "group block bg-bg-card rounded overflow-hidden border-2 border-border",
        "shadow-brutal hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-lg",
        "transition-all duration-100 shrink-0",
        size === "sm" && "w-36",
        size === "md" && "w-44",
        size === "lg" && "w-52",
        className,
      )}
    >
      {/* Square image — Spotify album art style */}
      <div className="relative aspect-square w-full overflow-hidden">
        {event.cover_image ? (
          <Image
            src={coverSrc ?? event.cover_image}
            alt={event.title}
            fill
            className="object-cover"
            sizes="180px"
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-primary/30 to-bg-elevated" />
        )}

        {/* Badges */}
        <div className="absolute top-1.5 left-1.5 flex gap-1">
          {event.is_trending && (
            <span className="px-1.5 py-0.5 rounded bg-primary text-on-primary text-[9px] font-bold uppercase flex items-center">
              <Flame size={9} aria-hidden />
            </span>
          )}
          {event.is_free && (
            <span className="px-1.5 py-0.5 rounded bg-success text-white text-[9px] font-bold uppercase">
              Free
            </span>
          )}
        </div>

        {/* Save */}
        <button
          onClick={toggleSave}
          aria-label={saved ? "Unsave event" : "Save event"}
          className={cn(
            "absolute top-1.5 right-1.5 p-1.5 rounded border border-white/30 transition-all",
            "bg-black/60 hover:bg-black/80",
            (saving || saveError) && "opacity-50",
          )}
        >
          {saveError
            ? <AlertCircle size={12} className="text-error" />
            : saved
            ? <BookmarkCheck size={12} className="text-primary" />
            : <Bookmark size={12} className="text-white" />}
        </button>
      </div>

      {/* Text below image */}
      <div className="p-2.5 space-y-0.5 border-t-2 border-border">
        <h3 className="font-bold text-text text-xs leading-tight line-clamp-2">
          {event.title}
        </h3>
        <p className="text-[11px] text-text-muted truncate">{event.venue_name}</p>
        {/* Short price form ("₦3k – ₦15k") so it fits beside the date on narrow cards; the row
            wraps rather than cutting anything off. Screen readers get the full price. */}
        <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5 pt-1">
          {/* relative: keeps the screen-reader text (sr-only = absolutely positioned) inside the
              card; unanchored, it sat outside the scrolling row and widened the whole page. */}
          <span className={cn("relative text-xs font-black whitespace-nowrap", event.is_free ? "text-success" : "text-primary")}
            title={formatPrice(event.is_free, event.price_min, event.price_max, event.currency)}>
            <span aria-hidden>{formatPrice(event.is_free, event.price_min, event.price_max, event.currency, { compact: true })}</span>
            <span className="sr-only">{formatPrice(event.is_free, event.price_min, event.price_max, event.currency)}</span>
          </span>
          <span className="text-[10px] text-text-disabled font-medium whitespace-nowrap">
            {formatEventDateShort(event.start_date)}
          </span>
        </div>
      </div>
    </Link>
  );
}
