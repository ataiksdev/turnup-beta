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
import Link from "next/link";
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
        <p className="text-text-secondary font-bold uppercase tracking-wide text-sm">User not found</p>
      </div>
    );
  }

  const displayEvents = tab === "events" ? events : saved;

  return (
    <div className="flex flex-col pb-4">
      <TopBar back title={`@${profile.username}`} />

      {/* Spotify-style hero banner */}
      <div className="relative h-52 bg-gradient-to-br from-primary/60 to-bg-elevated border-b-2 border-border overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />

        {/* Avatar — overlaid at bottom-left */}
        <div className="absolute -bottom-10 left-4">
          <div className="border-4 border-bg rounded-full shadow-brutal">
            <Avatar src={profile.avatar_url} name={profile.full_name} size="xl" verified={profile.is_verified} />
          </div>
        </div>
      </div>

      {/* Name + action — offset for avatar overlap */}
      <div className="flex items-end justify-between px-4 pt-3 pb-4" style={{ marginTop: "2.5rem" }}>
        <div>
          <h1 className="text-xl font-black text-text">{profile.full_name}</h1>
          <p className="text-xs text-text-muted font-bold uppercase tracking-widest">@{profile.username}</p>
        </div>
        <div className="flex gap-2">
          {isOwnProfile ? (
            <Link href="/profile/edit"><Button variant="secondary" size="sm">Edit Profile</Button></Link>
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

      {/* Stats — horizontal Spotify-style */}
      <div className="mx-4 grid grid-cols-4 border-2 border-border rounded shadow-brutal-sm mb-4">
        {[
          { label: "Followers", value: formatCount(profile.followers_count) },
          { label: "Following", value: formatCount(profile.following_count) },
          { label: "Hosted",    value: profile.events_hosted },
          { label: "Attended",  value: profile.events_attended },
        ].map(({ label, value }, i, arr) => (
          <div
            key={label}
            className={cn(
              "flex flex-col items-center py-3 gap-0.5",
              i < arr.length - 1 && "border-r-2 border-border",
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
      <div className="flex border-y-2 border-border mx-4 mb-4 rounded">
        {(["events", ...(isOwnProfile ? ["saved"] : [])] as Tab[]).map((t, i, arr) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "flex-1 py-2.5 text-[10px] font-black uppercase tracking-widest transition-colors",
              i < arr.length - 1 && "border-r-2 border-border",
              tab === t
                ? "bg-primary text-white"
                : "text-text-muted hover:text-text bg-bg-card",
            )}
          >
            {t === "saved" ? (
              <span className="flex items-center justify-center gap-1.5">
                <Bookmark size={11} /> Saved
              </span>
            ) : t}
          </button>
        ))}
      </div>

      {/* Events grid */}
      <div className="px-4">
        {displayEvents && displayEvents.length > 0 ? (
          <div className="grid grid-cols-2 gap-3">
            {displayEvents.map((e) => (
              <EventCard key={e.id} event={e} size="sm" className="w-full" />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            <span className="text-4xl">{tab === "saved" ? "🔖" : "🎟️"}</span>
            <p className="text-sm font-black text-text-secondary uppercase tracking-wide">
              {tab === "saved" ? "No saved events yet" : "No events hosted yet"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
