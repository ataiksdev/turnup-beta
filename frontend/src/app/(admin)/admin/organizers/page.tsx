"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi, AdminOrganizerVerification } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/Avatar";
import { BadgeCheck, Globe, Building2 } from "lucide-react";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const h = Math.floor(diff / 3600000);
  if (h < 1) return "just now";
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function VerificationRow({ req }: { req: AdminOrganizerVerification }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-verification-queue"] });

  const approveMutation = useMutation({
    mutationFn: () => adminApi.approveVerification(token!, req.user_id),
    onSuccess: invalidate,
  });

  const rejectMutation = useMutation({
    mutationFn: (n: string) => adminApi.rejectVerification(token!, req.user_id, n),
    onSuccess: () => {
      setRejecting(false);
      setNote("");
      invalidate();
    },
  });

  return (
    <div className="border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4 space-y-3">
      <div className="flex items-center gap-3">
        <Avatar src={req.avatar_url} name={req.full_name ?? req.username} size="md" />
        <div className="min-w-0 flex-1">
          <p className="font-black text-text-primary truncate">{req.full_name ?? req.username}</p>
          <p className="text-xs text-text-muted">@{req.username} · {req.events_hosted} events hosted</p>
        </div>
        <span className="text-[10px] text-text-muted shrink-0">{timeAgo(req.verification_requested_at ?? req.profile_created_at)}</span>
      </div>

      {(req.organization_name || req.website) && (
        <div className="space-y-1 text-xs text-text-muted">
          {req.organization_name && (
            <p className="flex items-center gap-1.5"><Building2 size={12} /> {req.organization_name}</p>
          )}
          {req.website && (
            <p className="flex items-center gap-1.5"><Globe size={12} /> {req.website}</p>
          )}
        </div>
      )}

      {req.organizer_bio && (
        <p className="text-xs text-text-secondary">{req.organizer_bio}</p>
      )}
      {req.verification_note && (
        <p className="text-xs text-text-muted italic">"{req.verification_note}"</p>
      )}

      {rejecting ? (
        <div className="space-y-2">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Explain what's missing (visible to the organizer)"
            rows={2}
            className="w-full rounded border-2 border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
          />
          <div className="flex gap-2">
            <Button size="sm" variant="danger" loading={rejectMutation.isPending} disabled={note.trim().length < 3}
              onClick={() => rejectMutation.mutate(note.trim())}>
              Confirm reject
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setRejecting(false)}>Cancel</Button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button size="sm" loading={approveMutation.isPending} onClick={() => approveMutation.mutate()}>
            Approve
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setRejecting(true)}>Reject</Button>
        </div>
      )}
    </div>
  );
}

export default function AdminOrganizersPage() {
  const { token } = useAuthStore();

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-verification-queue"],
    queryFn: () => adminApi.verificationQueue(token!),
    enabled: !!token,
  });

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="Organizer Verification" back />

      <div className="px-4 py-4 space-y-4">
        <p className="text-xs text-text-muted">
          Approving grants a visual trust badge only — it doesn't change what the organizer
          can do or bypass event review.
        </p>

        {error && <p className="text-red-500 text-sm">{(error as Error).message}</p>}

        {isLoading ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="animate-pulse bg-bg-elevated rounded h-32" />
            ))}
          </div>
        ) : data && data.length > 0 ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {data.map((req) => <VerificationRow key={req.user_id} req={req} />)}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 gap-3 border-2 border-dashed border-border rounded">
            <BadgeCheck size={36} className="text-border-strong" aria-hidden />
            <p className="text-sm font-black text-text-secondary uppercase tracking-wide">
              No pending requests
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
