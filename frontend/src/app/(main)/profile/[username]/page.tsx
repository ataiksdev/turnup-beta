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
import { Globe, MapPin, Bookmark } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/utils";

type Tab = "events" | "saved";

export default function ProfilePage() {
  const { username } = useParams<{ username: string }>();
  const { token, user: me } = useAuthStore();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("events");

  const { data: profile, isLoading } = useQuery({
    queryKey: ["user", username],
    queryFn: () => usersApi.get(username, token ?? undefined),
  });

  const { data: events } = useQuery({
    queryKey: ["user-events", username],
    queryFn: () => usersApi.events(username),
    enabled: tab === "events",
  });

  const { data: saved } = useQuery({
    queryKey: ["user-saved", username],
    queryFn: () => token ? usersApi.saved(username, token) : Promise.resolve([]),
    enabled: tab === "saved" && !!token && me?.username === username,
  });

  const followMutation = useMutation({
    mutationFn: () =>
      profile?.is_following
        ? socialApi.unfollow(token!, username)
        : socialApi.follow(token!, username),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["user", username] }),
  });

  const isOwnProfile = me?.username === username;
  const prefs = parsePreferences(profile?.category_preferences);

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
        <span className="text-5xl">👤</span>
        <p className="text-text-secondary">User not found</p>
      </div>
    );
  }

  const displayEvents = tab === "events" ? events : saved;

  return (
    <div className="flex flex-col pb-4">
      <TopBar back title={`@${profile.username}`} />

      {/* Profile header */}
      <div className="px-4 py-5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <Avatar src={profile.avatar_url} name={profile.full_name} size="xl" verified={profile.is_verified} />

          <div className="flex gap-2 mt-2">
            {isOwnProfile ? (
              <Button variant="secondary" size="sm">Edit Profile</Button>
            ) : token ? (
              <Button
                variant={profile.is_following ? "secondary" : "primary"}
                size="sm"
                loading={followMutation.isPending}
                onClick={() => followMutation.mutate()}
              >
                {profile.is_following ? "Following" : "Follow"}
              </Button>
            ) : null}
          </div>
        </div>

        <div>
          <h1 className="text-xl font-black text-text">{profile.full_name}</h1>
          <p className="text-sm text-text-muted">@{profile.username}</p>
        </div>

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

        {/* Stats */}
        <div className="grid grid-cols-4 gap-2 py-3 border-y border-border">
          {[
            { label: "Followers", value: formatCount(profile.followers_count) },
            { label: "Following", value: formatCount(profile.following_count) },
            { label: "Hosted",    value: profile.events_hosted },
            { label: "Attended",  value: profile.events_attended },
          ].map(({ label, value }) => (
            <div key={label} className="flex flex-col items-center gap-0.5">
              <span className="text-lg font-black text-text">{value}</span>
              <span className="text-[10px] text-text-muted">{label}</span>
            </div>
          ))}
        </div>

        {/* Category preferences */}
        {prefs.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs text-text-muted font-medium uppercase tracking-wide">Interests</p>
            <div className="flex flex-wrap gap-2">
              {prefs.map((p) => (
                <Badge key={p} variant="primary">{p}</Badge>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border px-4">
        {(["events", ...(isOwnProfile ? ["saved"] : [])] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "flex-1 py-3 text-sm font-medium capitalize transition-colors",
              tab === t
                ? "text-primary border-b-2 border-primary"
                : "text-text-muted hover:text-text-secondary",
            )}
          >
            {t === "saved" ? (
              <span className="flex items-center justify-center gap-1.5">
                <Bookmark size={14} /> Saved
              </span>
            ) : t}
          </button>
        ))}
      </div>

      {/* Events grid */}
      <div className="px-4 pt-4">
        {displayEvents && displayEvents.length > 0 ? (
          <div className="grid grid-cols-2 gap-3">
            {displayEvents.map((e) => (
              <EventCard key={e.id} event={e} size="sm" className="w-full" />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            <span className="text-4xl">{tab === "saved" ? "🔖" : "🎟️"}</span>
            <p className="text-sm text-text-secondary">
              {tab === "saved" ? "No saved events yet" : "No events hosted yet"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
