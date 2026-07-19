"use client";
import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { organizerApi, eventsApi } from "@/lib/api";
import type { CoHost } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Avatar } from "@/components/ui/Avatar";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";
import { UserPlus, X } from "lucide-react";

const STATUS_BADGE: Record<string, string> = {
  accepted: "bg-success/15 text-success border-success/40",
  invited:  "bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 border-yellow-300",
  declined: "bg-error/15 text-error border-error/40",
};

function CoHostRow({
  cohost,
  onRemove,
  removing,
}: {
  cohost: CoHost;
  onRemove: (cohostUserId: string) => void;
  removing: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const canRemove = cohost.status === "accepted" || cohost.status === "invited";

  return (
    <div className="flex items-center gap-3 p-3 rounded border-2 border-border bg-bg-card shadow-brutal-sm">
      <Avatar
        src={cohost.avatar_url}
        name={cohost.full_name || cohost.username}
        size="sm"
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-black text-text truncate">
          {cohost.full_name || cohost.username}
        </p>
        <p className="text-xs text-text-muted truncate">@{cohost.username}</p>
      </div>
      <span
        className={cn(
          "shrink-0 px-2 py-1 rounded border text-[10px] font-black uppercase tracking-widest",
          STATUS_BADGE[cohost.status] ?? STATUS_BADGE.declined,
        )}
      >
        {cohost.status}
      </span>
      {canRemove && (
        confirming ? (
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => {
                setConfirming(false);
                onRemove(cohost.user_id);
              }}
              disabled={removing}
              className="px-2 py-1 rounded border-2 border-error bg-error/10 text-[10px] font-black uppercase tracking-widest text-error hover:bg-error/20 transition-colors disabled:opacity-50"
            >
              Confirm
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="p-1 rounded hover:bg-bg-elevated transition-colors"
            >
              <X size={13} className="text-text-muted" />
            </button>
          </div>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            disabled={removing}
            className="shrink-0 px-2 py-1 rounded border-2 border-border text-[10px] font-black uppercase tracking-widest text-text-muted hover:text-error hover:border-error hover:bg-error/10 transition-colors disabled:opacity-50"
          >
            Remove
          </button>
        )
      )}
    </div>
  );
}

export default function CoHostsPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuthStore();
  const queryClient = useQueryClient();

  const [username, setUsername] = useState("");
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const { data: event } = useQuery({
    queryKey: ["event", id],
    queryFn: () => eventsApi.get(id, token ?? undefined),
  });

  const { data: cohosts, isLoading } = useQuery({
    queryKey: ["cohosts", id],
    queryFn: () => organizerApi.listCohosts(id),
  });

  const inviteMutation = useMutation({
    mutationFn: (uname: string) =>
      organizerApi.inviteCohost(token!, id, uname.replace(/^@/, "")),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cohosts", id] });
      setUsername("");
      setInviteError(null);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error ? err.message : "User not found or already a co-host.";
      setInviteError(msg.includes("404") || msg.toLowerCase().includes("not found")
        ? "User not found."
        : msg);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (cohostUserId: string) =>
      organizerApi.removeCohost(token!, id, cohostUserId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cohosts", id] });
      setRemovingId(null);
    },
    onSettled: () => {
      setRemovingId(null);
    },
  });

  function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim()) return;
    setInviteError(null);
    inviteMutation.mutate(username.trim());
  }

  function handleRemove(cohostUserId: string) {
    setRemovingId(cohostUserId);
    removeMutation.mutate(cohostUserId);
  }

  return (
    <div className="flex flex-col pb-6">
      <TopBar title="Co-hosts" back />

      {event && (
        <div className="px-4 pt-3 pb-1">
          <p className="text-xs text-text-muted font-black uppercase tracking-widest truncate">
            {event.title}
          </p>
        </div>
      )}

      <div className="px-4 pt-4 space-y-5">
        <form
          onSubmit={handleInvite}
          className="flex flex-col gap-2"
        >
          <label className="text-[10px] font-black uppercase tracking-widest text-text-muted">
            Invite by username
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                setInviteError(null);
              }}
              placeholder="@username"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              className="flex-1 rounded border-2 border-border bg-bg-card px-3 py-2.5 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-border-strong transition-colors"
            />
            <button
              type="submit"
              disabled={!username.trim() || inviteMutation.isPending}
              className="px-4 py-2.5 rounded border-2 border-border bg-primary text-white text-[10px] font-black uppercase tracking-widest hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {inviteMutation.isPending ? "Inviting…" : "Invite"}
            </button>
          </div>
          {inviteError && (
            <p className="text-xs font-black text-error">{inviteError}</p>
          )}
        </form>

        <div className="space-y-2">
          <p className="text-[10px] font-black uppercase tracking-widest text-text-muted">
            Co-hosts
          </p>

          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : !cohosts || cohosts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-14 gap-3 text-center rounded border-2 border-border bg-bg-card shadow-brutal-sm">
              <UserPlus size={32} className="text-border-strong" aria-hidden />
              <p className="font-black text-text text-sm uppercase tracking-wide">
                No co-hosts yet
              </p>
              <p className="text-xs text-text-muted max-w-[220px]">
                Invite someone by username to help manage this event.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {cohosts.map((c) => (
                <CoHostRow
                  key={c.id}
                  cohost={c}
                  onRemove={handleRemove}
                  removing={removingId === c.user_id && removeMutation.isPending}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
