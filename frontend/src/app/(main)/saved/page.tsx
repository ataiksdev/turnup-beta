"use client";
import { useQuery } from "@tanstack/react-query";
import { usersApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { EventCard } from "@/components/events/EventCard";
import { Skeleton } from "@/components/ui/Skeleton";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Bookmark, WifiOff } from "lucide-react";
import { useOfflineCopy } from "@/store/tickets";
import { useOffline } from "@/lib/network";

export default function SavedPage() {
  const { token, user } = useAuthStore();

  const { data: live, isLoading, isError } = useQuery({
    queryKey: ["saved", user?.username],
    queryFn: () => (token && user) ? usersApi.saved(user.username, token) : Promise.resolve([]),
    enabled: !!token && !!user,
  });
  // The copy kept on the phone (OfflineSync), whenever the live list isn't here.
  const copy = useOfflineCopy(user?.id);
  const offline = useOffline();
  const usingCopy = !live && copy.syncedAt !== null;
  const saved = live ?? (usingCopy ? copy.saved : undefined);

  if (!user || !token) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4 px-8 text-center">
        <Bookmark size={48} className="text-primary" aria-hidden />
        <h2 className="text-xl font-black text-text">Save your favourites</h2>
        <p className="text-sm text-text-secondary">Log in to bookmark events and find them later.</p>
        <Link href="/login"><Button fullWidth>Log In</Button></Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="Saved Events" />

      {usingCopy && (offline || isError) && (
        <div className="flex items-center gap-2 px-4 py-2 bg-bg-elevated border-b border-border text-xs text-text-muted">
          <WifiOff size={12} aria-hidden />
          <span>You&apos;re offline. Showing saved events kept on this phone.</span>
        </div>
      )}

      <div className="px-4 pt-4">
        {isLoading && !saved && !offline ? (
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-52 w-full" />
            ))}
          </div>
        ) : (isError || offline) && !saved ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
            <Bookmark size={40} className="text-border-strong" aria-hidden />
            <p className="text-text-secondary font-medium">{offline ? "You're offline" : "Could not load saved events"}</p>
            <p className="text-sm text-text-muted">
              {offline ? "Your saved events will show here once you're back online." : "Check your connection and try again"}
            </p>
          </div>
        ) : saved && saved.length > 0 ? (
          <div className="grid grid-cols-2 gap-3">
            {saved.map((e) => (
              <EventCard key={e.id} event={e} size="sm" className="w-full" />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
            <Bookmark size={40} className="text-border-strong" aria-hidden />
            <p className="text-text-secondary font-medium">No saved events yet</p>
            <p className="text-sm text-text-muted">Tap the bookmark on any event to save it here</p>
            <Link href="/search"><Button variant="secondary" size="sm">Browse Events</Button></Link>
          </div>
        )}
      </div>
    </div>
  );
}
