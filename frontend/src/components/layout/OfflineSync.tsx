"use client";
import { useEffect, useRef } from "react";
import { eventsApi, organizerApi, usersApi } from "@/lib/api";
import { clearOfflineImages, syncOfflineImages } from "@/lib/offlineImages";
import { OFFLINE_SYNC_EVENT } from "@/lib/network";
import { useAuthStore } from "@/store/auth";
import { useOfflineStore } from "@/store/tickets";
import type { Event } from "@/types";

const MAX_EVENTS = 40;                         // keeps storage bounded
const KEEP_PAST_MS = 3 * 24 * 60 * 60 * 1000;  // events that ended up to 3 days ago stay

/**
 * Keeps the offline copy (store/tickets.ts) of the signed-in user's tickets, saved events, the
 * pages of those events and their cover photos up to date: when the app opens online, when the
 * connection comes back, and right after buying or saving (lib/api.ts asks for a sync). When
 * nobody is signed in, the copy and the photos are deleted.
 */
export function OfflineSync() {
  const { token, hasHydrated } = useAuthStore();
  const userId = useAuthStore((s) => s.user?.id);
  const username = useAuthStore((s) => s.user?.username);
  const running = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!hasHydrated) return;
    if (!token || !userId || !username) {
      useOfflineStore.getState().clear();
      clearOfflineImages();
      return;
    }
    // Someone else signed in on this phone: drop the previous account's copy straight away.
    if (useOfflineStore.getState().userId && useOfflineStore.getState().userId !== userId) {
      useOfflineStore.getState().clear();
      clearOfflineImages();
    }

    const sync = async () => {
      if (running.current || !navigator.onLine) return;
      running.current = true;
      try {
        const [tickets, saved] = await Promise.all([
          organizerApi.myTickets(token),
          usersApi.saved(username, token),
        ]);
        const now = Date.now();
        const keep = (iso?: string | null) => !iso || new Date(iso).getTime() > now - KEEP_PAST_MS;
        const ids = [...new Set([
          ...tickets.filter((t) => t.status === "confirmed" && keep(t.event_date)).map((t) => t.event_id),
          ...saved.filter((e) => keep(e.end_date ?? e.start_date)).map((e) => e.id),
        ])].slice(0, MAX_EVENTS);
        const events = (await Promise.all(ids.map((id) => eventsApi.get(id, token).catch(() => null))))
          .filter((e): e is Event => !!e);
        // Still the same account? (it could have changed while this ran)
        if (useAuthStore.getState().user?.id !== userId) return;
        useOfflineStore.getState().replaceAll(userId, { tickets, saved, events });
        await syncOfflineImages([
          ...events.map((e) => e.cover_image),
          ...saved.map((e) => e.cover_image),
          ...tickets.map((t) => t.event_cover),
        ].filter((u): u is string => !!u));
      } catch { /* offline or server unreachable: keep the copy we have */ }
      finally { running.current = false; }
    };
    const soon = () => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(sync, 1500);
    };

    sync();
    window.addEventListener("online", soon);
    window.addEventListener(OFFLINE_SYNC_EVENT, soon);
    return () => {
      window.removeEventListener("online", soon);
      window.removeEventListener(OFFLINE_SYNC_EVENT, soon);
      if (timer.current) clearTimeout(timer.current);
    };
  }, [token, userId, username, hasHydrated]);

  return null;
}
