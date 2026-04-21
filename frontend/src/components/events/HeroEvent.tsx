"use client";
import { formatEventDate, formatPrice } from "@/lib/utils";
import type { Event } from "@/types";
import { Calendar, MapPin, Users, Flame } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { Avatar } from "@/components/ui/Avatar";

export function HeroEvent({ event }: { event: Event }) {
  return (
    <Link
      href={`/events/${event.slug}`}
      className="block relative h-[500px] overflow-hidden border-y-2 border-border"
    >
      {event.cover_image ? (
        <Image
          src={event.cover_image}
          alt={event.title}
          fill
          className="object-cover"
          priority
          sizes="100vw"
        />
      ) : (
        <div className="absolute inset-0 bg-gradient-to-br from-primary/40 to-bg-elevated" />
      )}

      {/* Deep gradient overlay for readability */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent" />

      {/* Top badges */}
      <div className="absolute top-4 left-4 flex gap-2">
        {event.is_trending && (
          <span className="flex items-center gap-1 px-2.5 py-1 bg-primary text-white text-[11px] font-bold uppercase tracking-wider border border-white/20 rounded">
            <Flame size={10} aria-hidden /> Hot right now
          </span>
        )}
        {event.category && (
          <span className="px-2.5 py-1 bg-black/60 text-white text-[11px] font-bold uppercase tracking-wider border border-white/20 rounded">
            {event.category.icon} {event.category.name}
          </span>
        )}
      </div>

      {/* Bottom content */}
      <div className="absolute bottom-0 left-0 right-0 px-5 pb-6 pt-12 space-y-3">
        <h1 className="text-3xl font-black text-white leading-tight drop-shadow-lg">
          {event.title}
        </h1>

        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 text-sm text-white/80">
            <Calendar size={13} className="text-primary shrink-0" />
            {formatEventDate(event.start_date)}
          </div>
          <div className="flex items-center gap-2 text-sm text-white/80">
            <MapPin size={13} className="text-primary shrink-0" />
            {event.venue_name} · {event.city}
          </div>
        </div>

        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-2">
            <Avatar src={event.host.avatar_url} name={event.host.full_name} size="sm" />
            <div className="flex flex-col">
              <span className="text-[11px] text-white/60 uppercase tracking-wide">Hosted by</span>
              <span className="text-xs text-white font-bold">@{event.host.username}</span>
            </div>
            <span className="flex items-center gap-1 text-xs text-white/60 ml-2">
              <Users size={11} /> {event.attendees_count.toLocaleString()} going
            </span>
          </div>
          <span className={`font-black text-base ${event.is_free ? "text-success" : "text-primary"}`}>
            {formatPrice(event.is_free, event.price_min, event.price_max)}
          </span>
        </div>
      </div>
    </Link>
  );
}
