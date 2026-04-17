import { FeedSkeleton } from "@/components/ui/Skeleton";

export default function Loading() {
  return (
    <div aria-busy="true" aria-label="Loading activity">
      <div className="h-14 bg-bg-surface border-b border-border" />
      <div className="pt-4">
        <FeedSkeleton />
      </div>
    </div>
  );
}
