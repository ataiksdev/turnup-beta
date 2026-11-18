"use client";
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Clock } from "lucide-react";
import { apiErrorMessage, eventsApi } from "@/lib/api";
import { routes } from "@/lib/routes";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/Button";
import { timeAgo } from "@/lib/utils";

/** Host view of an event's waitlist: who's waiting, in order, and "notify the next N"
 *  when spots open up (sends each of them an in-app notification). */
export function WaitlistPanel({ eventId }: { eventId: string }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const [count, setCount] = useState(1);
  const { data: entries } = useQuery({
    queryKey: ["waitlist", eventId],
    queryFn: () => eventsApi.waitlist(token!, eventId),
    enabled: !!token && !!eventId,
  });
  const notify = useMutation({
    mutationFn: () => eventsApi.notifyWaitlist(token!, eventId, count),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["waitlist", eventId] }),
  });

  if (!entries || entries.length === 0) return null;
  const waiting = entries.filter((e) => e.status === "waiting");

  return (
    <div className="bg-bg-card border-2 border-border rounded p-4 shadow-brutal-sm space-y-3">
      <p className="text-[10px] font-black uppercase tracking-widest text-text-muted flex items-center gap-1">
        <Clock size={12} /> Waitlist · {waiting.length} waiting
      </p>
      <ol className="divide-y-2 divide-border">
        {entries.map((e) => (
          <li key={e.id} className="py-2 flex items-center justify-between gap-2 text-sm">
            <Link href={routes.profile(e.username)} className="min-w-0 truncate">
              <span className="font-bold text-text">#{e.position}</span>{" "}
              <span className="text-text">{e.full_name || e.username}</span>{" "}
              <span className="text-text-muted">@{e.username}</span>
            </Link>
            <span className="text-xs text-text-muted shrink-0">
              {e.status === "notified" && e.notified_at ? `notified ${timeAgo(e.notified_at)}` : `joined ${timeAgo(e.created_at)}`}
            </span>
          </li>
        ))}
      </ol>
      {waiting.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <label htmlFor="notify-count" className="text-xs text-text-muted">Spots opened:</label>
          <input id="notify-count" type="number" min={1} max={Math.min(50, waiting.length)} value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
            className="w-16 h-8 bg-bg border-2 border-border rounded px-2 text-sm text-text" />
          <Button size="sm" loading={notify.isPending} onClick={() => notify.mutate()}>
            <BellRing size={14} /> Notify next {count}
          </Button>
        </div>
      )}
      {notify.isSuccess && (
        <p className="text-xs text-success">Notified {notify.data.count}: {notify.data.notified.map((u) => "@" + u).join(", ")}</p>
      )}
      {notify.isError && <p className="text-xs text-error">{apiErrorMessage(notify.error, "Could not notify the waitlist.")}</p>}
    </div>
  );
}
