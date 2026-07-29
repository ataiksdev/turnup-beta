"use client";
import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi, AdminUserOut } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

const ROLE_TABS: { value: string; label: string }[] = [
  { value: "",          label: "All" },
  { value: "attendee",  label: "Attendees" },
  { value: "organizer", label: "Organizers" },
  { value: "moderator", label: "Moderators" },
  { value: "admin",     label: "Admins" },
];

function RoleBadge({ role }: { role: string }) {
  const colors: Record<string, string> = {
    admin: "border-red-400 text-red-700 bg-red-50",
    moderator: "border-purple-400 text-purple-700 bg-purple-50",
    organizer: "border-blue-400 text-blue-700 bg-blue-50",
    attendee: "border-border text-text-muted bg-bg-elevated",
  };
  return (
    <span className={cn("text-xs font-bold px-2 py-0.5 rounded border-2 whitespace-nowrap", colors[role] ?? colors.attendee)}>
      {role}
    </span>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span className={cn(
      "text-xs font-bold px-2 py-0.5 rounded border-2 whitespace-nowrap",
      active
        ? "border-green-400 text-green-700 bg-green-50"
        : "border-red-400 text-red-700 bg-red-50",
    )}>
      {active ? "active" : "banned"}
    </span>
  );
}

function UserRow({ u, authUserId }: { u: AdminUserOut; authUserId: string }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const isSelf = u.id === authUserId;

  const mutation = useMutation({
    mutationFn: (body: { role?: string; is_active?: boolean; is_verified?: boolean }) =>
      adminApi.updateUser(token!, u.id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  const dicebear = `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(u.username)}`;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-2 border-border bg-bg-surface shadow-brutal-sm rounded px-3 py-2.5">
      <img
        src={dicebear}
        alt={u.username}
        className="w-9 h-9 rounded border-2 border-border shrink-0"
      />

      <div className="min-w-0 flex-1 basis-40">
        <p className="font-black text-text-primary text-sm truncate">@{u.username}</p>
        <p className="text-xs text-text-muted truncate">
          {[u.full_name ?? u.display_name, u.email].filter(Boolean).join(" · ")}
        </p>
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        <RoleBadge role={u.role} />
        <StatusBadge active={u.is_active} />
        {u.is_verified && (
          <span className="text-xs font-bold px-2 py-0.5 rounded border-2 border-emerald-400 text-emerald-700 bg-emerald-50 whitespace-nowrap">verified</span>
        )}
      </div>

      <p className="hidden xl:block text-xs text-text-muted shrink-0 whitespace-nowrap">
        {u.events_hosted} hosted · {u.events_attended} attended · {u.followers_count} followers
      </p>

      <div className="flex items-center gap-1.5 shrink-0 ml-auto">
        {isSelf ? (
          <p className="text-xs text-text-muted italic whitespace-nowrap">You</p>
        ) : (
          <>
            <Button
              size="sm"
              variant="secondary"
              loading={mutation.isPending}
              onClick={() => mutation.mutate({ is_active: !u.is_active })}
            >
              {u.is_active ? "Ban" : "Unban"}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              loading={mutation.isPending}
              onClick={() => mutation.mutate({ is_verified: !u.is_verified })}
            >
              {u.is_verified ? "Unverify" : "Verify"}
            </Button>
            <select
              value={u.role}
              disabled={mutation.isPending}
              onChange={(e) => mutation.mutate({ role: e.target.value })}
              className="text-xs font-bold border-2 border-border bg-bg-surface rounded px-2 py-1 text-text-primary"
            >
              <option value="attendee">attendee</option>
              <option value="organizer">organizer</option>
              <option value="moderator">moderator</option>
              <option value="admin">admin</option>
            </select>
          </>
        )}
      </div>
    </div>
  );
}

export default function AdminUsersPage() {
  const { token, user: authUser } = useAuthStore();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search]);

  const { data: users, isLoading, error } = useQuery({
    queryKey: ["admin-users", debouncedSearch, roleFilter],
    queryFn: () => adminApi.users(token!, {
      q: debouncedSearch || undefined,
      role: roleFilter || undefined,
    }),
    enabled: !!token,
  });

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="User Management" back />

      <div className="px-4 py-4 space-y-3">
        <Input
          placeholder="Search users..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          icon={<Search size={16} />}
        />

        <div className="flex flex-wrap gap-2">
          {ROLE_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setRoleFilter(tab.value)}
              className={cn(
                "text-xs font-bold px-3 py-1.5 rounded border-2 transition-colors",
                roleFilter === tab.value
                  ? "border-primary bg-primary text-white"
                  : "border-border bg-bg-surface text-text-muted",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {error && (
          <p className="text-red-500 text-sm">{(error as Error).message}</p>
        )}

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="animate-pulse bg-bg-elevated rounded h-16" />
            ))}
          </div>
        ) : users && users.length > 0 ? (
          <div className="space-y-2">
            {users.map((u) => (
              <UserRow key={u.id} u={u} authUserId={authUser?.id ?? ""} />
            ))}
          </div>
        ) : (
          <p className="text-center text-text-muted text-sm py-12">No users found</p>
        )}
      </div>
    </div>
  );
}
