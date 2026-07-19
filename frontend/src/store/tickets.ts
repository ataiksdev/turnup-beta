"use client";
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { TicketOrder } from "@/lib/api";

interface TicketCacheState {
  tickets: Record<string, TicketOrder>;
  setTickets: (tickets: TicketOrder[]) => void;
  setTicket: (ticket: TicketOrder) => void;
}

export const useTicketCache = create<TicketCacheState>()(
  persist(
    (set) => ({
      tickets: {},
      setTickets: (tickets) =>
        set((s) => ({
          tickets: {
            ...s.tickets,
            ...Object.fromEntries(tickets.map((t) => [t.id, t])),
          },
        })),
      setTicket: (ticket) =>
        set((s) => ({ tickets: { ...s.tickets, [ticket.id]: ticket } })),
    }),
    {
      name: "turnup-tickets",
      storage: createJSONStorage(() => {
        if (typeof window === "undefined")
          return { getItem: () => null, setItem: () => {}, removeItem: () => {} };
        return localStorage;
      }),
    },
  ),
);
