"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminApi, ScoutedItemOut } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import Link from "next/link";

const PAGE_SIZE = 50;

function StatusBadge({ status }: { status: ScoutedItemOut["status"] }) {
  const map: Record<ScoutedItemOut["status"], { label: string; cls: string }> = {
    created: { label: "created", cls: "border-green-400 text-green-700 bg-green-50" },
    skipped_duplicate: { label: "duplicate", cls: "border-blue-400 text-blue-700 bg-blue-50" },
    skipped_no_event: { label: "not an event", cls: "border-border text-text-muted bg-bg-elevated" },
    failed: { label: "failed", cls: "border-red-400 text-red-700 bg-red-50" },
  };
  const { label, cls } = map[status] ?? map.failed;
  return <span className={cn("text-xs font-bold px-2 py-0.5 rounded border-2 whitespace-nowrap", cls)}>{label}</span>;
}

function LogRow({ item }: { item: ScoutedItemOut }) {
  return (
    <div className="border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-3 space-y-1.5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-bold text-text-muted truncate">{item.source_name}</p>
        <StatusBadge status={item.status} />
      </div>
      <p className="text-xs font-mono text-text-secondary truncate">{item.url}</p>
      {item.event_title && (
        <p className="text-sm font-black text-text-primary truncate">→ {item.event_title}</p>
      )}
      {item.error_note && (
        <p className="text-xs text-red-600">{item.error_note}</p>
      )}
      <p className="text-[10px] text-text-muted">{new Date(item.created_at).toLocaleString("en-NG")}</p>
    </div>
  );
}

export default function ScoutLogPage() {
  const { token } = useAuthStore();
  const [skip, setSkip] = useState(0);
  const [allItems, setAllItems] = useState<ScoutedItemOut[]>([]);

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["admin-scout-log", skip],
    queryFn: async () => {
      const result = await adminApi.scoutLog(token!, { skip, limit: PAGE_SIZE });
      setAllItems((prev) => (skip === 0 ? result : [...prev, ...result]));
      return result;
    },
    enabled: !!token,
  });

  const hasMore = data && data.length === PAGE_SIZE;

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="Scout Run Log" back />

      <div className="px-4 py-4 space-y-3">
        <Link href="/admin/scout/sources" className="text-xs font-bold text-primary hover:underline">
          ← Back to Sources
        </Link>

        {error && <p className="text-red-500 text-sm">{(error as Error).message}</p>}

        {isLoading && skip === 0 ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="animate-pulse bg-bg-elevated rounded h-24" />
            ))}
          </div>
        ) : allItems.length > 0 ? (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
              {allItems.map((item) => <LogRow key={item.id} item={item} />)}
            </div>
            {hasMore && (
              <Button fullWidth variant="secondary" loading={isFetching} onClick={() => setSkip((s) => s + PAGE_SIZE)}>
                Load more
              </Button>
            )}
          </>
        ) : (
          <p className="text-center text-text-muted text-sm py-12">No scout activity yet</p>
        )}
      </div>
    </div>
  );
}
