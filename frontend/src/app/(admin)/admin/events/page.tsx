"use client";
import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi, AdminEventOut } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Search, Users, Eye } from "lucide-react";
import { cn } from "@/lib/utils";

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    published: "border-green-400 text-green-700 bg-green-50",
    draft: "border-border text-text-muted bg-bg-elevated",
    cancelled: "border-red-400 text-red-700 bg-red-50",
    completed: "border-blue-400 text-blue-700 bg-blue-50",
  };
  return (
    <span className={cn("text-xs font-bold px-2 py-0.5 rounded border-2", colors[status] ?? colors.draft)}>
      {status}
    </span>
  );
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-NG", { day: "2-digit", month: "short", year: "numeric" });
}

function EventRow({ ev }: { ev: AdminEventOut }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: (body: { is_featured?: boolean; is_trending?: boolean; status?: string }) =>
      adminApi.updateEvent(token!, ev.id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-events"] }),
  });

  return (
    <div className="border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4 space-y-3">
      <div>
        <p className="font-black text-text-primary">{ev.title}</p>
        <p className="text-xs text-text-muted">{ev.city} · @{ev.host_username}</p>
      </div>

      <div className="flex flex-wrap gap-1.5 items-center">
        <StatusBadge status={ev.status} />
        {ev.is_featured && (
          <span className="text-xs font-bold px-2 py-0.5 rounded border-2 border-yellow-400 text-yellow-700 bg-yellow-50">featured</span>
        )}
        {ev.is_trending && (
          <span className="text-xs font-bold px-2 py-0.5 rounded border-2 border-orange-400 text-orange-700 bg-orange-50">trending</span>
        )}
      </div>

      <div className="flex items-center gap-4 text-xs text-text-muted">
        <span className="flex items-center gap-1"><Users size={12} />{ev.attendees_count.toLocaleString("en-NG")}</span>
        <span className="flex items-center gap-1"><Eye size={12} />{ev.views_count.toLocaleString("en-NG")}</span>
        <span>{formatDate(ev.start_date)}</span>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <Button
          size="sm"
          variant="secondary"
          loading={mutation.isPending}
          onClick={() => mutation.mutate({ is_featured: !ev.is_featured })}
        >
          {ev.is_featured ? "★ Featured" : "☆ Feature"}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          loading={mutation.isPending}
          onClick={() => mutation.mutate({ is_trending: !ev.is_trending })}
        >
          {ev.is_trending ? "🔥 Trending" : "🔥 Trend"}
        </Button>
        <select
          value={ev.status}
          disabled={mutation.isPending}
          onChange={(e) => mutation.mutate({ status: e.target.value })}
          className="text-xs font-bold border-2 border-border bg-bg-surface rounded px-2 py-1 text-text-primary"
        >
          <option value="published">published</option>
          <option value="draft">draft</option>
          <option value="cancelled">cancelled</option>
          <option value="completed">completed</option>
        </select>
      </div>
    </div>
  );
}

export default function AdminEventsPage() {
  const { token } = useAuthStore();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search]);

  const { data: events, isLoading, error } = useQuery({
    queryKey: ["admin-events", debouncedSearch, statusFilter],
    queryFn: () => adminApi.events(token!, {
      q: debouncedSearch || undefined,
      status: statusFilter || undefined,
    }),
    enabled: !!token,
  });

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="Event Moderation" back />

      <div className="px-4 py-4 space-y-3">
        <div className="flex gap-2">
          <div className="flex-1">
            <Input
              placeholder="Search events..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              icon={<Search size={16} />}
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-xs font-bold border-2 border-border bg-bg-surface rounded px-3 py-2 text-text-primary shrink-0"
          >
            <option value="">All</option>
            <option value="published">Published</option>
            <option value="draft">Draft</option>
            <option value="cancelled">Cancelled</option>
            <option value="completed">Completed</option>
          </select>
        </div>

        {error && (
          <p className="text-red-500 text-sm">{(error as Error).message}</p>
        )}

        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="animate-pulse bg-bg-elevated rounded h-36" />
            ))}
          </div>
        ) : events && events.length > 0 ? (
          <div className="space-y-3">
            {events.map((ev) => (
              <EventRow key={ev.id} ev={ev} />
            ))}
          </div>
        ) : (
          <p className="text-center text-text-muted text-sm py-12">No events found</p>
        )}
      </div>
    </div>
  );
}
