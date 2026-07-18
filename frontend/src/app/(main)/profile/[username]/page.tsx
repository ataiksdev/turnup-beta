"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { usersApi, socialApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { EventCard } from "@/components/events/EventCard";
import { parsePreferences, formatCount } from "@/lib/utils";
import { Globe, MapPin, Bookmark, CheckCircle2, Heart, Ticket, UserX, LogOut, X, type LucideIcon } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";

type Tab = "events" | "attending" | "saved";

export default function ProfilePage() {
  const { username } = useParams<{ username: string }>();
  const { token, user: me, logout } = useAuthStore();
  const router = useRouter();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("events");
  const [showPast, setShowPast] = useState(false);
  const [followError, setFollowError] = useState("");
  const [followListModal, setFollowListModal] = useState<null | "followers" | "following">(null);

  const { data: profile, isLoading } = useQuery({
    queryKey: ["user", username],
    queryFn: () => usersApi.get(username, token ?? undefined),
  });

  const eventsQuery = useQuery({
    queryKey: ["user-events", username, showPast],
    queryFn: () => usersApi.events(username, showPast),
    enabled: tab === "events",
  });

  const attendingQuery = useQuery({
    queryKey: ["user-attending", username, showPast],
    queryFn: () => token ? usersApi.attending(username, token, showPast) : Promise.resolve([]),
    enabled: tab === "attending" && !!token && me?.username === username,
  });

  const savedQuery = useQuery({
    queryKey: ["user-saved", username],
    queryFn: () => token ? usersApi.saved(username, token) : Promise.resolve([]),
    enabled: tab === "saved" && !!token && me?.username === username,
  });

  const followListQuery = useQuery({
    queryKey: ["follow-list", username, followListModal],
    queryFn: () =>
      followListModal === "followers"
        ? usersApi.followers(username)
        : usersApi.following(username),
    enabled: !!followListModal,
  });

  const followMutation = useMutation({
    mutationFn: () =>
      profile?.is_following
        ? socialApi.unfollow(token!, username)
        : socialApi.follow(token!, username),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["user", username] }),
    onError: () => {
      setFollowError("Could not update follow. Please try again.");
      setTimeout(() => setFollowError(""), 3000);
    },
  });

  const isOwnProfile = me?.username === username;
  const prefs = parsePreferences(profile?.category_preferences);

  const tabs: Tab[] = isOwnProfile ? ["events", "attending", "saved"] : ["events"];

  const activeQuery = tab === "events" ? eventsQuery : tab === "attending" ? attendingQuery : savedQuery;
  const displayEvents = activeQuery.data;

  const EMPTY: Record<Tab, { icon: LucideIcon; label: string }> = {
    events:    { icon: Ticket,   label: showPast ? "No past events hosted" : "No upcoming events hosted" },
    attending: { icon: Ticket,   label: showPast ? "No past events attended" : "No upcoming events" },
    saved:     { icon: Bookmark, label: "No saved events yet" },
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-3">
        <UserX size={40} className="text-border-strong" aria-hidden />
        <p className="text-text-secondary font-bold uppercase tracking-wide text-sm">User not found</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col pb-4">
      <TopBar back title={`@${profile.username}`} />

      {/* Spotify-style hero banner */}
      <div className="relative h-52 bg-gradient-to-br from-primary/60 to-bg-elevated border-b-2 border-border overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
        <div className="absolute -bottom-10 left-4">
          <div className="border-4 border-bg rounded-full shadow-brutal">
            <Avatar src={profile.avatar_url} name={profile.full_name} size="xl" verified={profile.is_verified} />
          </div>
        </div>
      </div>

      {/* Name + action */}
      <div className="flex items-end justify-between px-4 pt-3 pb-4" style={{ marginTop: "2.5rem" }}>
        <div>
          <h1 className="text-xl font-black text-text">{profile.full_name}</h1>
          <p className="text-xs text-text-muted font-bold uppercase tracking-widest">@{profile.username}</p>
        </div>
        <div className="flex gap-2">
          {isOwnProfile ? (
            <>
              <Link href="/profile/edit"><Button variant="secondary" size="sm">Edit Profile</Button></Link>
              <button
                onClick={() => { logout(); router.replace("/login"); }}
                aria-label="Log out"
                className="p-2 rounded border-2 border-border bg-bg-card hover:border-error hover:text-error transition-colors shadow-brutal-sm"
              >
                <LogOut size={15} aria-hidden />
              </button>
            </>
          ) : token ? (
            <div className="flex flex-col items-end gap-1">
              <Button
                variant={profile.is_following ? "secondary" : "primary"}
                size="sm"
                loading={followMutation.isPending}
                onClick={() => followMutation.mutate()}
              >
                {profile.is_following ? "Following" : "Follow"}
              </Button>
              {followError && (
                <p className="text-[10px] text-error font-medium">{followError}</p>
              )}
            </div>
          ) : null}
        </div>
      </div>

      {/* Bio + links */}
      <div className="px-4 space-y-2 pb-4">
        {profile.bio && (
          <p className="text-sm text-text-secondary leading-relaxed">{profile.bio}</p>
        )}
        <div className="flex flex-wrap gap-3 text-xs text-text-muted">
          {profile.location && (
            <span className="flex items-center gap-1">
              <MapPin size={12} className="text-primary" /> {profile.location}
            </span>
          )}
          {profile.website && (
            <a href={profile.website} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1 text-primary">
              <Globe size={12} /> {profile.website.replace(/^https?:\/\//, "")}
            </a>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="mx-4 grid grid-cols-4 border-2 border-border rounded shadow-brutal-sm mb-4">
        {[
          { label: "Followers", value: formatCount(profile.followers_count), onClick: () => setFollowListModal("followers") },
          { label: "Following", value: formatCount(profile.following_count), onClick: () => setFollowListModal("following") },
          { label: "Hosted",    value: profile.events_hosted, onClick: undefined },
          { label: "Attended",  value: profile.events_attended, onClick: undefined },
        ].map(({ label, value, onClick }, i, arr) => (
          <div
            key={label}
            role={onClick ? "button" : undefined}
            tabIndex={onClick ? 0 : undefined}
            onClick={onClick}
            onKeyDown={onClick ? (e) => e.key === "Enter" && onClick() : undefined}
            className={cn(
              "flex flex-col items-center py-3 gap-0.5",
              i < arr.length - 1 && "border-r-2 border-border",
              onClick && "cursor-pointer hover:bg-bg-elevated active:bg-bg-elevated transition-colors",
            )}
          >
            <span className="text-lg font-black text-text">{value}</span>
            <span className="text-[9px] font-bold text-text-muted uppercase tracking-widest">{label}</span>
          </div>
        ))}
      </div>

      {/* Interests */}
      {prefs.length > 0 && (
        <div className="px-4 space-y-2 pb-4">
          <p className="text-[10px] font-black text-text-muted uppercase tracking-widest">Interests</p>
          <div className="flex flex-wrap gap-2">
            {prefs.map((p) => (
              <Badge key={p} variant="primary">{p}</Badge>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-y-2 border-border mx-4 mb-3 rounded overflow-hidden">
        {tabs.map((t, i, arr) => (
          <button
            key={t}
            onClick={() => { setTab(t); setShowPast(false); }}
            className={cn(
              "flex-1 py-2.5 text-[10px] font-black uppercase tracking-widest transition-colors",
              i < arr.length - 1 && "border-r-2 border-border",
              tab === t ? "bg-primary text-white" : "text-text-muted hover:text-text bg-bg-card",
            )}
          >
            {t === "saved" ? (
              <span className="flex items-center justify-center gap-1"><Bookmark size={10} /> Saved</span>
            ) : t === "attending" ? (
              <span className="flex items-center justify-center gap-1"><CheckCircle2 size={10} /> Attending</span>
            ) : (
              "Events"
            )}
          </button>
        ))}
      </div>

      {/* Past / Upcoming toggle for events and attending tabs */}
      {(tab === "events" || tab === "attending") && (
        <div className="flex mx-4 mb-4 gap-2">
          <button
            onClick={() => setShowPast(false)}
            className={cn(
              "flex-1 py-1.5 text-[10px] font-black uppercase tracking-widest rounded border-2 transition-colors",
              !showPast ? "border-primary text-primary bg-primary/10" : "border-border text-text-muted bg-bg-card hover:border-primary/50",
            )}
          >
            Upcoming
          </button>
          <button
            onClick={() => setShowPast(true)}
            className={cn(
              "flex-1 py-1.5 text-[10px] font-black uppercase tracking-widest rounded border-2 transition-colors",
              showPast ? "border-primary text-primary bg-primary/10" : "border-border text-text-muted bg-bg-card hover:border-primary/50",
            )}
          >
            Past
          </button>
        </div>
      )}

      {/* Events grid */}
      <div className="px-4">
        {activeQuery.isLoading ? (
          <div className="flex justify-center py-10">
            <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          </div>
        ) : activeQuery.isError ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            {(() => { const Icon = EMPTY[tab].icon; return <Icon size={36} className="text-border-strong" aria-hidden />; })()}
            <p className="text-sm font-black text-error uppercase tracking-wide">Failed to load</p>
            <p className="text-xs text-text-muted">Check your connection and try again</p>
          </div>
        ) : displayEvents && displayEvents.length > 0 ? (
          <div className="grid grid-cols-2 gap-3">
            {displayEvents.map((e) => (
              <EventCard key={e.id} event={e} size="sm" className="w-full" />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            {(() => { const Icon = EMPTY[tab].icon; return <Icon size={36} className="text-border-strong" aria-hidden />; })()}
            <p className="text-sm font-black text-text-secondary uppercase tracking-wide">
              {EMPTY[tab].label}
            </p>
          </div>
        )}
      </div>

      {/* Followers / Following bottom-sheet modal */}
      {followListModal && (
        <div
          className="fixed inset-0 z-50 flex flex-col justify-end bg-black/50"
          onClick={() => setFollowListModal(null)}
        >
          <div
            className="bg-bg rounded-t-2xl border-t-2 border-border max-h-[70vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b-2 border-border">
              <p className="font-black text-text uppercase tracking-widest text-xs">
                {followListModal === "followers" ? "Followers" : "Following"}
              </p>
              <button
                onClick={() => setFollowListModal(null)}
                aria-label="Close"
                className="p-1 rounded hover:bg-bg-elevated transition-colors"
              >
                <X size={16} className="text-text-muted" aria-hidden />
              </button>
            </div>
            <div className="overflow-y-auto flex-1 divide-y divide-border">
              {followListQuery.isLoading ? (
                <div className="flex justify-center py-10">
                  <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                </div>
              ) : followListQuery.data && followListQuery.data.length > 0 ? (
                followListQuery.data.map((u) => (
                  <Link
                    key={u.id}
                    href={`/profile/${u.username}`}
                    onClick={() => setFollowListModal(null)}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-bg-elevated transition-colors"
                  >
                    <Avatar src={u.avatar_url} name={u.full_name} size="sm" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-text leading-none">{u.full_name}</p>
                      <p className="text-xs text-text-muted mt-0.5">@{u.username}</p>
                    </div>
                  </Link>
                ))
              ) : (
                <div className="py-14 text-center">
                  <p className="text-sm text-text-muted">
                    {followListModal === "followers" ? "No followers yet" : "Not following anyone yet"}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
