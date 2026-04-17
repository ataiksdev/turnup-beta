import { CarouselSkeleton, HeroSkeleton } from "@/components/ui/Skeleton";

export default function Loading() {
  return (
    <div className="flex flex-col gap-6 pb-4" aria-busy="true" aria-label="Loading events">
      <div className="h-14" /> {/* TopBar placeholder */}
      <div className="px-4 space-y-1">
        <div className="h-7 w-44 bg-bg-elevated rounded-2xl animate-shimmer skeleton-shimmer" />
        <div className="h-4 w-56 bg-bg-elevated rounded-xl animate-shimmer skeleton-shimmer" />
      </div>
      <HeroSkeleton />
      <CarouselSkeleton />
      <CarouselSkeleton />
    </div>
  );
}
