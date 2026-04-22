"use client";
import { cn, formatEventDate, formatPrice, parseTags } from "@/lib/utils";
import type { Event } from "@/types";
import { AlertCircle, Calendar, MapPin, Users, Bookmark, BookmarkCheck, Tag } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Avatar } from "@/components/ui/Avatar";

interface ForYouCardProps {
  event: Event;
  rank: 1 | 2 | 3;
  /** Optional reason label shown as a badge */
  reason?: string;
}

const RANK_STYLES: Record<number, string> = {
  1: "bg-primary text-white",
  2: "bg-bg-elevated text-text border-2 border-border",
  3: "bg-bg-elevated text-text border-2 border-border",
};

export function ForYouCard({ event, rank, reason }: ForYouCardProps) {
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

  const tags = parseTags(event.tags).slice(0, 3);

  return (
    <Link
      href={`/events/${event.slug}`}
      className={cn(
        "group block bg-bg-card rounded border-2 border-border overflow-hidden",
        "shadow-brutal hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-lg",
        "transition-all duration-100",
        rank === 1 && "shadow-brutal-primary",
      )}
    >
      {/* Cover image */}
      <div className="relative w-full aspect-[16/7] overflow-hidden">
        {event.cover_image ? (
          <Image
            src={event.cover_image}
            alt={event.title}
            fill
            className="object-cover"
            sizes="(max-width: 512px) 100vw, 512px"
            priority={rank === 1}
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-primary/30 to-bg-elevated" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />

        {/* Rank badge */}
        <span className={cn(
          "absolute top-3 left-3 w-7 h-7 rounded flex items-center justify-center",
          "text-xs font-black border-2 border-border",
          RANK_STYLES[rank],
        )}>
          {rank}
        </span>

        {/* Save button */}
        <button
          onClick={toggleSave}
          aria-label={saved ? "Unsave event" : "Save event"}
          className={cn(
            "absolute top-3 right-3 p-1.5 rounded border border-white/30 transition-all",
            "bg-black/60 hover:bg-black/80",
            (saving || saveError) && "opacity-50",
          )}
        >
          {saveError
            ? <AlertCircle size={14} className="text-error" />
            : saved
            ? <BookmarkCheck size={14} className="text-primary" />
            : <Bookmark size={14} className="text-white" />}
        </button>

        {/* Reason badge at bottom of image */}
        {reason && (
          <span className="absolute bottom-3 left-3 px-2 py-0.5 bg-primary text-white text-[10px] font-black uppercase tracking-wider rounded">
            {reason}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="p-3 space-y-2 border-t-2 border-border">
        {event.category && (
          <p className="text-[10px] font-black text-primary uppercase tracking-widest">
            {event.category.name}
          </p>
        )}

        <h3 className="font-black text-text text-sm leading-tight line-clamp-2">
          {event.title}
        </h3>

        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
            <Calendar size={11} className="text-primary shrink-0" aria-hidden />
            {formatEventDate(event.start_date)}
          </div>
          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
            <MapPin size={11} className="text-primary shrink-0" aria-hidden />
            <span className="truncate">{event.venue_name} · {event.city}</span>
          </div>
        </div>

        <div className="flex items-center justify-between pt-0.5">
          <div className="flex items-center gap-2">
            <Avatar src={event.host.avatar_url} name={event.host.full_name} size="xs" />
            <span className="text-[10px] text-text-muted truncate max-w-[100px]">
              @{event.host.username}
            </span>
            <span className="flex items-center gap-0.5 text-[10px] text-text-disabled">
              <Users size={9} aria-hidden />
              {event.attendees_count.toLocaleString()}
            </span>
          </div>
          <span className={cn("text-sm font-black", event.is_free ? "text-success" : "text-primary")}>
            {formatPrice(event.is_free, event.price_min, event.price_max, event.currency)}
          </span>
        </div>

        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {tags.map((t) => (
              <Link
                key={t}
                href={`/search?tag=${encodeURIComponent(t)}`}
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-0.5 px-1.5 py-0.5 bg-bg-elevated border border-border rounded text-[9px] font-bold text-text-muted hover:text-primary hover:border-primary transition-colors"
              >
                <Tag size={8} aria-hidden />
                {t}
              </Link>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}
