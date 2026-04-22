"use client";
import { useQuery } from "@tanstack/react-query";
import { usersApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { EventCard } from "@/components/events/EventCard";
import { Skeleton } from "@/components/ui/Skeleton";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Bookmark } from "lucide-react";

export default function SavedPage() {
  const { token, user } = useAuthStore();

  const { data: saved, isLoading, isError } = useQuery({
    queryKey: ["saved", user?.username],
    queryFn: () => (token && user) ? usersApi.saved(user.username, token) : Promise.resolve([]),
    enabled: !!token && !!user,
  });

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

      <div className="px-4 pt-4">
        {isLoading ? (
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-52 w-full" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
            <Bookmark size={40} className="text-border-strong" aria-hidden />
            <p className="text-text-secondary font-medium">Could not load saved events</p>
            <p className="text-sm text-text-muted">Check your connection and try again</p>
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
