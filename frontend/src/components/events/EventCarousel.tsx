import { EventCard } from "./EventCard";
import { EventCardSkeleton } from "@/components/ui/Skeleton";
import type { Event } from "@/types";
import Link from "next/link";

interface EventCarouselProps {
  title: string;
  events?: Event[];
  loading?: boolean;
  seeAllHref?: string;
  cardSize?: "sm" | "md" | "lg";
}

export function EventCarousel({
  title, events, loading, seeAllHref, cardSize = "md",
}: EventCarouselProps) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between px-4">
        <h2 className="text-xs font-black text-text uppercase tracking-widest">{title}</h2>
        {seeAllHref && (
          <Link
            href={seeAllHref}
            className="text-[10px] font-black text-primary uppercase tracking-widest hover:text-primary/80 transition-colors"
          >
            See all
          </Link>
        )}
      </div>

      <div className="snap-scroll px-4 pb-2">
        {loading
          ? Array.from({ length: 4 }).map((_, i) => <EventCardSkeleton key={i} />)
          : events?.map((e) => <EventCard key={e.id} event={e} size={cardSize} />)}
      </div>
    </section>
  );
}
