"use client";
import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { seriesApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Skeleton } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { AlertCircle, Edit2, Eye, RefreshCw, Trash2 } from "lucide-react";

const STATUS_STYLES: Record<string, string> = {
  published: "bg-success/15 text-success border-success/40",
  draft:     "bg-bg-elevated text-text-muted border-border",
  cancelled: "bg-error/15 text-error border-error/40",
  completed: "bg-info/15 text-info border-info/40",
};

const RULE_LABELS: Record<string, string> = {
  "weekly": "Weekly",
  "bi-weekly": "Bi-Weekly",
  "monthly": "Monthly",
  "bi-monthly": "Bi-Monthly",
};

export default function SeriesDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { token } = useAuthStore();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const { data: series, isLoading, error } = useQuery({
    queryKey: ["series", id],
    queryFn: () => seriesApi.get(id),
    enabled: !!id,
  });

  async function handleDelete() {
    if (!token || !id) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await seriesApi.delete(token, id);
      router.replace("/organizer/events");
    } catch (err: any) {
      setDeleteError(err.message ?? "Failed to delete series");
      setDeleting(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col min-h-screen bg-bg">
        <TopBar back title="Series" />
        <div className="px-4 py-5 space-y-4">
          <Skeleton className="h-8 w-3/4" />
          <Skeleton className="h-5 w-1/3" />
          <div className="space-y-3 mt-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error || !series) {
    return (
      <div className="flex flex-col min-h-screen bg-bg">
        <TopBar back title="Series" />
        <div className="flex flex-col items-center justify-center flex-1 gap-3 px-4">
          <AlertCircle size={40} className="text-border-strong" aria-hidden />
          <p className="text-text-secondary text-sm">Series not found</p>
          <Link href="/organizer/events" className="text-primary text-sm font-medium">
            ← Back to My Events
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-bg">
      <TopBar back title={series.title} />

      <div className="px-4 py-5 space-y-6 pb-12">
        {/* Header */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <RefreshCw size={16} className="text-primary shrink-0" aria-hidden />
            <span className={cn(
              "px-2 py-1 rounded border text-[10px] font-black uppercase tracking-widest",
              "border-primary/40 bg-primary/10 text-primary",
            )}>
              {RULE_LABELS[series.recurrence_rule] ?? series.recurrence_rule}
            </span>
            <span className="text-xs text-text-muted">
              {series.events.length} {series.events.length === 1 ? "occurrence" : "occurrences"}
            </span>
          </div>
          {series.description && (
            <p className="text-sm text-text-secondary leading-relaxed">{series.description}</p>
          )}
        </div>

        {/* Occurrences */}
        <section className="space-y-3">
          <h2 className="text-xs font-black text-text uppercase tracking-widest">Occurrences</h2>
          {series.events.length === 0 ? (
            <p className="text-xs text-text-muted text-center py-6">No occurrences yet</p>
          ) : (
            <div className="space-y-2">
              {series.events.map((ev, i) => (
                <div
                  key={ev.id}
                  className="rounded border-2 border-border bg-bg-card shadow-brutal-sm overflow-hidden"
                >
                  <div className="flex items-center gap-3 p-3">
                    {/* Number badge */}
                    <span className="w-7 h-7 rounded bg-primary/10 border border-primary/30 flex items-center justify-center text-[10px] font-black text-primary shrink-0">
                      #{i + 1}
                    </span>

                    {/* Date + status */}
                    <div className="flex-1 min-w-0 space-y-0.5">
                      <p className="text-sm font-semibold text-text truncate">
                        {format(new Date(ev.start_date), "EEE, MMM d · h:mm a")}
                      </p>
                      <p className="text-xs text-text-muted">
                        {ev.attendees_count.toLocaleString()} attendees
                      </p>
                    </div>

                    {/* Status badge */}
                    <span className={cn(
                      "shrink-0 px-2 py-1 rounded border text-[10px] font-black uppercase tracking-widest",
                      STATUS_STYLES[ev.status] ?? STATUS_STYLES.draft,
                    )}>
                      {ev.status}
                    </span>
                  </div>

                  {/* Action bar */}
                  <div className="flex border-t-2 border-border divide-x-2 divide-border">
                    <Link
                      href={`/organizer/events/${ev.id}/edit`}
                      className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-[10px] font-black uppercase tracking-widest text-text-muted hover:text-text hover:bg-bg-elevated transition-colors"
                    >
                      <Edit2 size={11} /> Edit
                    </Link>
                    <Link
                      href={`/events/${ev.slug}`}
                      className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-[10px] font-black uppercase tracking-widest text-text-muted hover:text-text hover:bg-bg-elevated transition-colors"
                    >
                      <Eye size={11} /> View
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Delete series */}
        <section className="pt-4 border-t-2 border-border space-y-3">
          <h2 className="text-xs font-black text-error uppercase tracking-widest">Danger Zone</h2>
          {deleteError && (
            <p className="text-xs text-error">{deleteError}</p>
          )}
          {confirmDelete ? (
            <div className="space-y-2">
              <p className="text-sm text-text-secondary">
                This will permanently delete the series and all its events. This cannot be undone.
              </p>
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  loading={deleting}
                  onClick={handleDelete}
                  className="border-error bg-error text-white hover:bg-error/90"
                >
                  <Trash2 size={14} className="mr-1" />
                  Yes, Delete Series
                </Button>
                <Button
                  variant="secondary"
                  disabled={deleting}
                  onClick={() => setConfirmDelete(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-2 px-4 py-3 rounded border-2 border-error/40 bg-error/5 text-sm font-black text-error uppercase tracking-widest hover:bg-error/10 transition-colors"
            >
              <Trash2 size={14} />
              Delete Series
            </button>
          )}
        </section>
      </div>
    </div>
  );
}
