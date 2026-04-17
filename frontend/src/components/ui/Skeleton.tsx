import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("skeleton-shimmer rounded-2xl bg-bg-elevated", className)}
    />
  );
}

// ── Event card skeleton ────────────────────────────────────────────────────────

export function EventCardSkeleton({ size = "md" }: { size?: "sm" | "md" }) {
  const w = size === "sm" ? "w-full" : "w-64 shrink-0";
  return (
    <div aria-hidden="true" className={cn("rounded-3xl bg-bg-card overflow-hidden", w)}>
      <Skeleton className="h-40 w-full rounded-none" />
      <div className="p-3 space-y-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-3 w-1/3" />
      </div>
    </div>
  );
}

// ── Event carousel skeleton ────────────────────────────────────────────────────

export function CarouselSkeleton() {
  return (
    <section aria-hidden="true" className="space-y-3">
      <div className="flex items-center justify-between px-4">
        <Skeleton className="h-5 w-36" />
        <Skeleton className="h-4 w-14" />
      </div>
      <div className="snap-scroll px-4">
        {[...Array(3)].map((_, i) => <EventCardSkeleton key={i} />)}
      </div>
    </section>
  );
}

// ── Hero skeleton ──────────────────────────────────────────────────────────────

export function HeroSkeleton() {
  return (
    <div aria-hidden="true" className="mx-4">
      <Skeleton className="h-[420px] w-full rounded-3xl" />
    </div>
  );
}

// ── Event detail skeleton ──────────────────────────────────────────────────────

export function EventDetailSkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col pb-8 animate-fade-in">
      <Skeleton className="h-72 w-full rounded-none" />
      <div className="px-4 mt-4 space-y-5">
        <Skeleton className="h-4 w-20" />
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-6 w-3/4" />
        </div>
        <div className="space-y-2.5">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="h-5 w-1/2" />
        </div>
        <Skeleton className="h-20 w-full rounded-2xl" />
        <div className="flex gap-2">
          <Skeleton className="h-11 flex-1 rounded-2xl" />
          <Skeleton className="h-11 w-28 rounded-2xl" />
        </div>
        <Skeleton className="h-20 w-full rounded-2xl" />
        <div className="space-y-2">
          <Skeleton className="h-5 w-16" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </div>
    </div>
  );
}

// ── Profile skeleton ───────────────────────────────────────────────────────────

export function ProfileSkeleton() {
  return (
    <div aria-hidden="true" className="animate-fade-in">
      <Skeleton className="h-32 w-full rounded-none" />
      <div className="px-4">
        <div className="flex items-end justify-between -mt-8 mb-4">
          <Skeleton className="h-20 w-20 rounded-full" />
          <Skeleton className="h-9 w-24 rounded-xl" />
        </div>
        <div className="space-y-2">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-full" />
        </div>
        <div className="flex gap-4 mt-4">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-14 flex-1 rounded-2xl" />)}
        </div>
      </div>
      <div className="mt-6 px-4 space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="rounded-3xl bg-bg-card overflow-hidden">
            <Skeleton className="h-36 w-full rounded-none" />
            <div className="p-3 space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Feed / notifications skeleton ─────────────────────────────────────────────

export function FeedItemSkeleton() {
  return (
    <div aria-hidden="true" className="flex gap-3 px-4 py-2">
      <Skeleton className="h-10 w-10 rounded-full shrink-0" />
      <div className="flex-1 space-y-1.5 pt-1">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  );
}

export function FeedSkeleton() {
  return (
    <div aria-hidden="true" className="space-y-1">
      {[...Array(6)].map((_, i) => <FeedItemSkeleton key={i} />)}
    </div>
  );
}
