"use client";
import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { EventCard } from "@/components/events/EventCard";

/** "You might also like": what people who went to this event also went to, then similar
 *  events (GET /events/{id}/similar). Shows nothing when there's nothing to suggest. */
export function SimilarEvents({ eventId, title = "You might also like", surface = "similar" }: {
  eventId: string; title?: string; surface?: string;
}) {
  const { token } = useAuthStore();
  const { data } = useQuery({
    queryKey: ["events", "similar", eventId, !!token],
    queryFn: () => eventsApi.similar(eventId, 8, token ?? undefined),
    staleTime: 5 * 60_000,
  });
  if (!data?.length) return null;
  return (
    <section aria-labelledby={`similar-${eventId}`}>
      <h2 id={`similar-${eventId}`} className="mb-3 flex items-center gap-2 text-xs font-black text-text uppercase tracking-widest">
        <Sparkles size={14} className="text-primary" aria-hidden /> {title}
      </h2>
      <div className="snap-scroll gap-3 pb-1">
        {data.map((e, i) => (
          <div key={e.id} className="w-44 shrink-0 space-y-1">
            <EventCard event={e} size="sm" className="w-full" tracking={{ surface, position: i }} />
            {e.rec_reason && <p className="text-[10px] font-bold text-text-muted line-clamp-2">{e.rec_reason}</p>}
          </div>
        ))}
      </div>
    </section>
  );
}
