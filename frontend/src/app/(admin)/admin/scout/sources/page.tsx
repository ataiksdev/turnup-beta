"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi, ScoutSourceOut, ScoutRunResult } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Radar, ScrollText, Play } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "never";
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(dateStr).toLocaleDateString("en-NG", { day: "2-digit", month: "short" });
}

function SourceRow({ source }: { source: ScoutSourceOut }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const toggleMutation = useMutation({
    mutationFn: () => adminApi.updateScoutSource(token!, source.id, { is_active: !source.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-scout-sources"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => adminApi.deleteScoutSource(token!, source.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-scout-sources"] }),
  });

  return (
    <div className="border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-black text-text-primary truncate">{source.name}</p>
          <p className="text-xs text-text-muted truncate font-mono">{source.url}</p>
        </div>
        <span className={cn(
          "shrink-0 text-xs font-bold px-2 py-0.5 rounded border-2",
          source.is_active
            ? "border-green-400 text-green-700 bg-green-50"
            : "border-border text-text-muted bg-bg-elevated",
        )}>
          {source.is_active ? "active" : "paused"}
        </span>
      </div>

      <p className="text-xs text-text-muted">
        Last polled {timeAgo(source.last_polled_at)}
        {source.last_run_status && ` · ${source.last_run_status}`}
      </p>

      <div className="flex gap-2">
        <Button size="sm" variant="secondary" loading={toggleMutation.isPending} onClick={() => toggleMutation.mutate()}>
          {source.is_active ? "Pause" : "Resume"}
        </Button>
        {confirmDelete ? (
          <>
            <Button size="sm" variant="danger" loading={deleteMutation.isPending} onClick={() => deleteMutation.mutate()}>
              Confirm Delete
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setConfirmDelete(false)}>Cancel</Button>
          </>
        ) : (
          <Button size="sm" variant="secondary" className="border-red-300 text-red-600 hover:bg-red-50" onClick={() => setConfirmDelete(true)}>
            Delete
          </Button>
        )}
      </div>
    </div>
  );
}

function AddSourceForm() {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");

  const mutation = useMutation({
    mutationFn: () => adminApi.createScoutSource(token!, { name, url }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-scout-sources"] });
      setName(""); setUrl("");
    },
  });

  return (
    <div className="lg:max-w-xl border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4 space-y-3">
      <h3 className="text-xs font-black text-text-primary uppercase tracking-widest">Add RSS Source</h3>
      <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Lagos Events Blog" />
      <Input label="RSS/Atom feed URL" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/feed.xml" />
      <Button size="sm" loading={mutation.isPending} disabled={!name || !url} onClick={() => mutation.mutate()}>
        Add Source
      </Button>
      {mutation.error && <p className="text-red-500 text-sm">{(mutation.error as Error).message}</p>}
    </div>
  );
}

export default function ScoutSourcesPage() {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const [runResult, setRunResult] = useState<ScoutRunResult | null>(null);

  const { data: sources, isLoading, error } = useQuery({
    queryKey: ["admin-scout-sources"],
    queryFn: () => adminApi.scoutSources(token!),
    enabled: !!token,
  });

  const runMutation = useMutation({
    mutationFn: () => adminApi.runScoutNow(token!),
    onSuccess: (result) => {
      setRunResult(result);
      qc.invalidateQueries({ queryKey: ["admin-scout-sources"] });
    },
  });

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="AI Scout" back actions={
        <Link href="/admin/scout/log" aria-label="View run log" className="p-2 rounded hover:bg-bg-elevated transition-colors">
          <ScrollText size={18} className="text-text-secondary" />
        </Link>
      } />

      <div className="px-4 py-4 space-y-4 lg:max-w-4xl">
        <p className="text-xs text-text-muted">
          The scout agent checks these RSS/Atom feeds daily, drafts anything that looks like a
          real event with Claude, and submits it for your approval in the Events queue — same
          as a moderator submission, just automated.
        </p>

        <Button variant="secondary" loading={runMutation.isPending} onClick={() => runMutation.mutate()}>
          <Play size={14} /> Run Now
        </Button>

        {runResult && (
          <div className="border-2 border-primary/40 bg-primary/5 rounded p-3 text-xs text-text-secondary space-y-0.5">
            <p className="font-black text-text-primary uppercase tracking-wide text-[10px] mb-1">Run complete</p>
            <p>{runResult.sources_polled} source(s) polled · {runResult.items_seen} new item(s) seen</p>
            <p>{runResult.events_created} event(s) created for review · {runResult.skipped_duplicate} duplicate(s) skipped</p>
            <p>{runResult.skipped_no_event} not-an-event · {runResult.failed} failed</p>
          </div>
        )}

        {error && <p className="text-red-500 text-sm">{(error as Error).message}</p>}

        <div className="space-y-3">
          <h2 className="text-xs font-black text-text-primary uppercase tracking-widest flex items-center gap-1.5">
            <Radar size={12} /> Sources
          </h2>
          {isLoading ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="animate-pulse bg-bg-elevated rounded h-24" />
              ))}
            </div>
          ) : sources && sources.length > 0 ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {sources.map((s) => <SourceRow key={s.id} source={s} />)}
            </div>
          ) : (
            <p className="text-center text-text-muted text-sm py-8">No sources yet — add one below.</p>
          )}
        </div>

        <AddSourceForm />
      </div>
    </div>
  );
}
