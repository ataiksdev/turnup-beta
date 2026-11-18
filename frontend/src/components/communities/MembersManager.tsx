"use client";
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { apiErrorMessage, communitiesApi } from "@/lib/api";
import { routes } from "@/lib/routes";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/Button";

type Role = "member" | "moderator" | "admin";

/** Community admins: change members' roles and remove members. The server enforces the rules
 *  (creator can't be demoted/removed, the last admin can't be demoted); this shows its reasons. */
export function MembersManager({ slug, creatorId }: { slug: string; creatorId: string }) {
  const { token, user } = useAuthStore();
  const qc = useQueryClient();
  const [error, setError] = useState("");
  const { data: members } = useQuery({
    queryKey: ["community-members", slug],
    queryFn: () => communitiesApi.members(slug, 1, token ?? undefined),
    enabled: !!slug,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["community-members", slug] });
  const setRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: Role }) =>
      communitiesApi.setMemberRole(token!, slug, userId, role),
    onSuccess: () => { setError(""); refresh(); },
    onError: (e) => setError(apiErrorMessage(e, "Could not change that role.")),
  });
  const remove = useMutation({
    mutationFn: (userId: string) => communitiesApi.removeMember(token!, slug, userId),
    onSuccess: () => {
      setError(""); refresh();
      qc.invalidateQueries({ queryKey: ["community", slug] });
    },
    onError: (e) => setError(apiErrorMessage(e, "Could not remove that member.")),
  });

  if (!members) return null;
  return (
    <div className="p-4 rounded border-2 border-border bg-bg-card space-y-3">
      <p className="text-xs font-black uppercase tracking-widest text-text-muted flex items-center gap-1">
        <Users size={12} /> Members ({members.length})
      </p>
      {error && <p role="alert" className="text-xs text-error">{error}</p>}
      <ul className="divide-y-2 divide-border">
        {members.map((m) => {
          const isCreator = m.user_id === creatorId;
          const isMe = m.user_id === user?.id;
          return (
            <li key={m.user_id} className="py-2 flex items-center justify-between gap-2">
              <Link href={routes.profile(m.username)} className="min-w-0 truncate text-sm">
                <span className="font-bold text-text">{m.display_name || m.full_name || m.username}</span>{" "}
                <span className="text-text-muted">@{m.username}{isCreator ? " · creator" : ""}</span>
              </Link>
              <div className="flex items-center gap-2 shrink-0">
                <label className="sr-only" htmlFor={`role-${m.user_id}`}>Role for {m.username}</label>
                <select
                  id={`role-${m.user_id}`}
                  value={m.role}
                  disabled={(isCreator && !isMe) || setRole.isPending}
                  onChange={(e) => setRole.mutate({ userId: m.user_id, role: e.target.value as Role })}
                  className="h-8 bg-bg border-2 border-border rounded px-1 text-xs text-text"
                >
                  <option value="member">Member</option>
                  <option value="moderator">Moderator</option>
                  <option value="admin">Admin</option>
                </select>
                {!isCreator && !isMe && (
                  <Button size="xs" variant="secondary" loading={remove.isPending && remove.variables === m.user_id}
                    onClick={() => { if (confirm(`Remove @${m.username} from the community?`)) remove.mutate(m.user_id); }}>
                    Remove
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
