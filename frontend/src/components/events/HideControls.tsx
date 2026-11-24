"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { EyeOff, UserX } from "lucide-react";
import { discoveryApi, apiErrorMessage, type HiddenKind } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

/** "Not interested" and "Hide this organizer" on an event page. Hidden things drop out of every
 *  feed and search for this person (not from direct links), and can be brought back here or in
 *  Settings. */
export function HideControls({ eventId, hostId, hostName }: { eventId: string; hostId: string; hostName: string }) {
  const { token, user } = useAuthStore();
  const qc = useQueryClient();
  const [hidden, setHidden] = useState<HiddenKind | null>(null);
  const [error, setError] = useState("");

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["events"] });
    qc.invalidateQueries({ queryKey: ["hidden"] });
  };
  const hide = useMutation({
    mutationFn: (kind: HiddenKind) => discoveryApi.hide(token!, kind, kind === "event" ? eventId : hostId),
    onSuccess: (_, kind) => { setHidden(kind); setError(""); refresh(); },
    onError: (err) => setError(apiErrorMessage(err, "Couldn't hide that. Try again.")),
  });
  const undo = useMutation({
    mutationFn: (kind: HiddenKind) => discoveryApi.unhide(token!, kind, kind === "event" ? eventId : hostId),
    onSuccess: () => { setHidden(null); refresh(); },
    onError: (err) => setError(apiErrorMessage(err, "Couldn't undo that. Try again.")),
  });

  if (!token || !user || user.id === hostId) return null;

  if (hidden) {
    return (
      <div role="status" className="flex items-center justify-between gap-3 p-3 rounded border-2 border-border bg-bg-card text-xs">
        <span className="text-text-secondary">
          {hidden === "event"
            ? "Got it. You won't see this event in your feeds or searches."
            : `Done. You won't see events from ${hostName} in your feeds or searches.`}
        </span>
        <button onClick={() => undo.mutate(hidden)} disabled={undo.isPending}
          className="shrink-0 font-bold text-primary hover:underline disabled:opacity-50">
          Undo
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-center gap-4 text-xs text-text-muted">
        <button onClick={() => hide.mutate("event")} disabled={hide.isPending}
          className="flex items-center gap-1.5 hover:text-text-secondary disabled:opacity-50">
          <EyeOff size={12} aria-hidden /> Not interested
        </button>
        <span aria-hidden>·</span>
        <button onClick={() => hide.mutate("organizer")} disabled={hide.isPending}
          className="flex items-center gap-1.5 hover:text-text-secondary disabled:opacity-50">
          <UserX size={12} aria-hidden /> Hide this organizer
        </button>
      </div>
      {error && <p className="text-xs text-error text-center">{error}</p>}
    </div>
  );
}
