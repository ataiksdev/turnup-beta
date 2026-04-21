"use client";
import { useQuery } from "@tanstack/react-query";
import { usersApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Skeleton } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";
import { BarChart2, CalendarPlus, Edit2, Users, Eye, Ticket } from "lucide-react";
import Link from "next/link";
import { cn, formatEventDateShort, formatPrice } from "@/lib/utils";
import type { Event } from "@/types";

const STATUS_STYLES: Record<string, string> = {
  published: "bg-success/15 text-success border-success/40",
  draft:     "bg-bg-elevated text-text-muted border-border",
  cancelled: "bg-error/15 text-error border-error/40",
  completed: "bg-[#3B82F6]/15 text-[#3B82F6] border-[#3B82F6]/40",
};

function EventRow({ event }: { event: Event }) {
  return (
    <div className="flex flex-col gap-0 rounded border-2 border-border bg-bg-card shadow-brutal-sm overflow-hidden">
      <Link
        href={`/events/${event.slug}`}
        className="flex items-center gap-3 p-4 hover:bg-bg-elevated transition-colors"
      >
        {/* Cover thumbnail */}
        <div className="w-14 h-14 rounded border-2 border-border shrink-0 overflow-hidden bg-gradient-to-br from-primary/30 to-bg-elevated">
          {event.cover_image && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={event.cover_image} alt="" className="w-full h-full object-cover" />
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0 space-y-1">
          <p className="font-black text-text text-sm truncate">{event.title}</p>
          <p className="text-xs text-text-muted truncate">{event.venue_name} · {formatEventDateShort(event.start_date)}</p>
          <div className="flex items-center gap-3 text-xs text-text-muted">
            <span className="flex items-center gap-1"><Users size={11} /> {event.attendees_count}</span>
            <span>{formatPrice(event.is_free, event.price_min, event.price_max)}</span>
          </div>
        </div>

        {/* Status badge */}
        <span className={cn(
          "shrink-0 px-2 py-1 rounded border text-[10px] font-black uppercase tracking-widest",
          STATUS_STYLES[event.status] ?? STATUS_STYLES.draft,
        )}>
          {event.status}
        </span>
      </Link>

      {/* Action bar */}
      <div className="flex border-t-2 border-border divide-x-2 divide-border">
        <Link
          href={`/organizer/events/${event.id}/edit`}
          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-[10px] font-black uppercase tracking-widest text-text-muted hover:text-text hover:bg-bg-elevated transition-colors"
        >
          <Edit2 size={11} /> Edit
        </Link>
        <Link
          href={`/organizer/events/${event.id}/analytics`}
          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-[10px] font-black uppercase tracking-widest text-text-muted hover:text-text hover:bg-bg-elevated transition-colors"
        >
          <BarChart2 size={11} /> Analytics
        </Link>
        <Link
          href={`/events/${event.slug}`}
          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-[10px] font-black uppercase tracking-widest text-text-muted hover:text-text hover:bg-bg-elevated transition-colors"
        >
          <Eye size={11} /> View
        </Link>
      </div>
    </div>
  );
}

export default function OrganizerEventsPage() {
  const { user } = useAuthStore();

  const { data: events, isLoading } = useQuery({
    queryKey: ["user-events", user?.username],
    queryFn: () => usersApi.events(user!.username),
    enabled: !!user?.username,
  });

  const published = events?.filter((e) => e.status === "published") ?? [];
  const drafts    = events?.filter((e) => e.status === "draft")     ?? [];
  const past      = events?.filter((e) => e.status === "completed" || e.status === "cancelled") ?? [];

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="My Events" />

      {/* Create CTA */}
      <div className="px-4 py-4">
        <Link href="/organizer/create">
          <Button fullWidth size="lg">
            <CalendarPlus size={16} className="mr-2" /> Create New Event
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="px-4 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : !events || events.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-center px-4">
          <Ticket size={40} className="text-border-strong" aria-hidden />
          <p className="font-black text-text-secondary text-sm uppercase tracking-wide">No events yet</p>
          <p className="text-xs text-text-muted">Create your first event and start selling tickets</p>
        </div>
      ) : (
        <div className="px-4 space-y-6">
          {published.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-xs font-black text-text uppercase tracking-widest">
                Published <span className="text-primary">({published.length})</span>
              </h2>
              {published.map((e) => <EventRow key={e.id} event={e} />)}
            </section>
          )}

          {drafts.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-xs font-black text-text uppercase tracking-widest">
                Drafts <span className="text-text-muted">({drafts.length})</span>
              </h2>
              {drafts.map((e) => <EventRow key={e.id} event={e} />)}
            </section>
          )}

          {past.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-xs font-black text-text uppercase tracking-widest">
                Past <span className="text-text-muted">({past.length})</span>
              </h2>
              {past.map((e) => <EventRow key={e.id} event={e} />)}
            </section>
          )}
        </div>
      )}
    </div>
  );
}
