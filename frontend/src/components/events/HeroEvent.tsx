"use client";
import { formatEventDate, formatPrice } from "@/lib/utils";
import type { Event } from "@/types";
import { Calendar, MapPin, Users } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/Avatar";

export function HeroEvent({ event }: { event: Event }) {
  return (
    <Link href={`/events/${event.slug}`} className="block relative h-[420px] overflow-hidden rounded mx-4 border-2 border-border shadow-brutal"  >
      {event.cover_image && (
        <Image
          src={event.cover_image}
          alt={event.title}
          fill
          className="object-cover"
          priority
          sizes="100vw"
        />
      )}
      <div className="absolute inset-0 bg-hero-overlay" />

      {/* Trending badge */}
      {event.is_trending && (
        <div className="absolute top-4 left-4">
          <span className="px-3 py-1 rounded bg-primary text-white text-xs font-bold uppercase tracking-wider border border-white/30">
            🔥 Hot right now
          </span>
        </div>
      )}

      {/* Content */}
      <div className="absolute bottom-0 left-0 right-0 p-5 space-y-3">
        {event.category && (
          <span className="text-xs font-medium text-text-secondary uppercase tracking-widest">
            {event.category.icon} {event.category.name}
          </span>
        )}

        <h1 className="text-2xl font-black text-white leading-tight">{event.title}</h1>

        <div className="space-y-1.5">
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <Calendar size={13} className="text-primary" />
            {formatEventDate(event.start_date)}
          </div>
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <MapPin size={13} className="text-primary" />
            {event.venue_name} · {event.city}
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Avatar src={event.host.avatar_url} name={event.host.full_name} size="sm" />
            <span className="text-xs text-text-secondary">by {event.host.username}</span>
            <span className="flex items-center gap-1 text-xs text-text-muted">
              <Users size={11} /> {event.attendees_count.toLocaleString()} going
            </span>
          </div>
          <span className={`font-bold text-sm ${event.is_free ? "text-success" : "text-primary"}`}>
            {formatPrice(event.is_free, event.price_min, event.price_max)}
          </span>
        </div>
      </div>
    </Link>
  );
}
