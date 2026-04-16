"use client";
import { cn, formatEventDateShort, formatPrice } from "@/lib/utils";
import type { Event } from "@/types";
import { Bookmark, BookmarkCheck, Users } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

interface EventCardProps {
  event: Event;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function EventCard({ event, size = "md", className }: EventCardProps) {
  const { token } = useAuthStore();
  const [saved, setSaved] = useState(event.is_saved);
  const [saving, setSaving] = useState(false);

  async function toggleSave(e: React.MouseEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setSaving(true);
    try {
      const res = await eventsApi.save(token, event.id);
      setSaved(res.saved);
    } catch { /* swallow */ } finally {
      setSaving(false);
    }
  }

  const isSmall = size === "sm";

  return (
    <Link
      href={`/events/${event.slug}`}
      className={cn(
        "group block bg-bg-card rounded-3xl overflow-hidden border border-border",
        "hover:border-border-strong transition-all duration-200 hover:shadow-card",
        "shrink-0 active:scale-[0.98]",
        size === "sm" && "w-48",
        size === "md" && "w-64",
        size === "lg" && "w-72",
        className,
      )}
    >
      {/* Image */}
      <div className={cn("relative overflow-hidden", isSmall ? "h-32" : "h-44")}>
        {event.cover_image ? (
          <Image
            src={event.cover_image}
            alt={event.title}
            fill
            className="object-cover group-hover:scale-105 transition-transform duration-500"
            sizes="(max-width: 768px) 256px, 288px"
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-primary/20 to-bg-elevated" />
        )}
        <div className="absolute inset-0 bg-card-overlay" />

        {/* Badges */}
        <div className="absolute top-2 left-2 flex gap-1.5">
          {event.is_trending && (
            <span className="px-2 py-0.5 rounded-full bg-primary text-white text-[10px] font-bold uppercase tracking-wide">
              🔥 Trending
            </span>
          )}
          {event.is_free && (
            <span className="px-2 py-0.5 rounded-full bg-success/90 text-white text-[10px] font-bold uppercase tracking-wide">
              Free
            </span>
          )}
        </div>

        {/* Save button */}
        <button
          onClick={toggleSave}
          className={cn(
            "absolute top-2 right-2 p-1.5 rounded-full transition-all",
            "bg-bg/60 backdrop-blur-sm hover:bg-bg/80",
            saving && "opacity-50",
          )}
        >
          {saved
            ? <BookmarkCheck size={14} className="text-primary" />
            : <Bookmark size={14} className="text-white" />}
        </button>

        {/* Date pill */}
        <div className="absolute bottom-2 left-2 px-2 py-0.5 rounded-full bg-bg/70 backdrop-blur-sm">
          <span className="text-[10px] font-medium text-text">
            {formatEventDateShort(event.start_date)}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="p-3 space-y-1.5">
        <h3 className={cn("font-semibold text-text leading-snug line-clamp-2",
          isSmall ? "text-xs" : "text-sm")}>
          {event.title}
        </h3>

        <p className="text-[11px] text-text-muted truncate">{event.venue_name} · {event.city}</p>

        <div className="flex items-center justify-between">
          <span className={cn("font-bold", isSmall ? "text-xs" : "text-sm",
            event.is_free ? "text-success" : "text-primary")}>
            {formatPrice(event.is_free, event.price_min, event.price_max)}
          </span>
          <span className="flex items-center gap-1 text-[11px] text-text-muted">
            <Users size={10} />
            {event.attendees_count.toLocaleString()}
          </span>
        </div>
      </div>
    </Link>
  );
}
