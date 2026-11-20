"use client";
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { TicketOrder } from "@/lib/api";
import type { Event } from "@/types";

/**
 * What the app keeps on the phone for offline use, for ONE signed-in account: their tickets
 * (with the codes the door scans), their saved events, their upcoming RSVPs (going /
 * interested), and the full event pages for all of them (My Vibes works offline from this).
 * Filled by OfflineSync when the app opens online and after buying or saving; wiped on logout
 * (and whenever a different account signs in), so the next person on the phone can't see it.
 * Cover photos are kept separately in the browser's Cache Storage (lib/offlineImages.ts).
 */
interface OfflineState {
  userId: string | null;
  tickets: Record<string, TicketOrder>;
  saved: Event[];
  attending: Event[];
  events: Record<string, Event>;
  syncedAt: string | null;
  /** Replace everything for this account (a full sync). */
  replaceAll: (userId: string, data: { tickets: TicketOrder[]; saved: Event[]; attending: Event[]; events: Event[] }) => void;
  /** Keep one ticket / event the user just looked at. */
  setTicket: (userId: string, ticket: TicketOrder) => void;
  setEvent: (userId: string, event: Event) => void;
  clear: () => void;
}

const EMPTY = { userId: null, tickets: {}, saved: [], attending: [], events: {}, syncedAt: null };

export const useOfflineStore = create<OfflineState>()(
  persist(
    (set, get) => ({
      ...EMPTY,
      replaceAll: (userId, { tickets, saved, attending, events }) => set({
        userId,
        tickets: Object.fromEntries(tickets.map((t) => [t.id, t])),
        saved,
        attending,
        events: Object.fromEntries(events.map((e) => [e.id, e])),
        syncedAt: new Date().toISOString(),
      }),
      setTicket: (userId, ticket) => {
        const s = get();
        const base = s.userId === userId ? s.tickets : {};
        set({ ...(s.userId === userId ? {} : EMPTY), userId, tickets: { ...base, [ticket.id]: ticket } });
      },
      setEvent: (userId, event) => {
        const s = get();
        // Only events the account has a ticket for or saved: other pages aren't kept.
        if (s.userId !== userId || !s.events[event.id]) return;
        set({ events: { ...s.events, [event.id]: event } });
      },
      clear: () => set(EMPTY),
    }),
    {
      name: "turnup-offline",
      storage: createJSONStorage(() => {
        if (typeof window === "undefined")
          return { getItem: () => null, setItem: () => {}, removeItem: () => {} };
        // The old ticket cache wasn't tied to an account: drop it.
        try { localStorage.removeItem("turnup-tickets"); } catch { /* storage blocked */ }
        return localStorage;
      }),
      partialize: (s) => ({ userId: s.userId, tickets: s.tickets, saved: s.saved, attending: s.attending, events: s.events, syncedAt: s.syncedAt }),
    },
  ),
);

/** The offline copy for the signed-in user only (empty for anyone else). */
export function useOfflineCopy(userId: string | undefined | null) {
  const s = useOfflineStore();
  const mine = !!userId && s.userId === userId;
  return {
    tickets: mine ? s.tickets : {},
    saved: mine ? s.saved : [],
    attending: mine ? (s.attending ?? []) : [],
    events: mine ? s.events : {},
    syncedAt: mine ? s.syncedAt : null,
  };
}
