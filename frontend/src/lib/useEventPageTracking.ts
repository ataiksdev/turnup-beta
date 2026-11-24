"use client";
import { useCallback, useEffect, useRef } from "react";
import { takeClick, track } from "@/lib/track";
import type { Event } from "@/types";

const daysUntil = (iso: string) => Math.round((new Date(iso).getTime() - Date.now()) / 864e5 * 10) / 10;

/**
 * Everything the event page reports (docs/recommendations-spec.md): the view and where it came
 * from, time on the page and how far down they read, seeing the tickets and the map, choosing
 * tickets, and leaving with tickets chosen but not paid for. Purchases themselves are recorded
 * by the server.
 */
export function useEventPageTracking(event: Event | undefined, cart: { value: number; count: number }, purchased: boolean) {
  const ticketsRef = useRef<HTMLElement | null>(null);
  const mapRef = useRef<HTMLDivElement | null>(null);
  const state = useRef({ cart, purchased, abandoned: false, sawMap: false, sawTickets: false });
  state.current.cart = cart;
  state.current.purchased = purchased;

  const eventId = event?.id;
  const startDate = event?.start_date;

  useEffect(() => {
    if (!eventId || !startDate) return;
    const s = state.current;
    Object.assign(s, { abandoned: false, sawMap: false, sawTickets: false });
    const origin = takeClick(eventId);
    track("event_viewed", {
      event_id: eventId, surface: origin?.surface ?? "direct", position: origin?.position,
      rec_request_id: origin?.rec_request_id ?? null,
      props: { days_until_event: daysUntil(startDate) },
    });

    // Time actually looking at the page (not while the app is in the background).
    let visibleMs = 0;
    let since: number | null = document.visibilityState === "visible" ? Date.now() : null;
    let maxScroll = 0;
    const onVisibility = () => {
      if (document.visibilityState === "hidden" && since !== null) { visibleMs += Date.now() - since; since = null; }
      else if (document.visibilityState === "visible" && since === null) since = Date.now();
    };
    const onScroll = () => {
      const h = document.documentElement.scrollHeight - window.innerHeight;
      if (h > 0) maxScroll = Math.max(maxScroll, Math.min(100, Math.round((window.scrollY / h) * 100)));
    };
    // Leaving the page: a route change runs the cleanup below; closing the tab or app, or a
    // full page load, only fires pagehide (React doesn't unmount then).
    let ended = false;
    const end = () => {
      if (ended) return;
      ended = true;
      if (since !== null) visibleMs += Date.now() - since;
      track("event_dwell_ended", {
        event_id: eventId,
        props: { dwell_seconds: Math.round(visibleMs / 1000), scroll_depth_pct: maxScroll,
                 viewed_map: s.sawMap, viewed_tickets: s.sawTickets },
      });
      if (s.cart.count > 0 && !s.purchased && !s.abandoned) {
        track("checkout_abandoned", { event_id: eventId,
          props: { step: "tier_select", cart_value: s.cart.value, ticket_count: s.cart.count } });
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pagehide", end);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", end);
      end();
    };
  }, [eventId, startDate]);

  // Seeing the ticket list counts as opening the "drawer"; seeing the map is noted on the dwell.
  useEffect(() => {
    if (!eventId || typeof IntersectionObserver === "undefined") return;
    const observers: IntersectionObserver[] = [];
    const watch = (el: Element | null, onSeen: () => void) => {
      if (!el) return;
      const o = new IntersectionObserver(([entry]) => {
        if (entry.isIntersecting) { onSeen(); o.disconnect(); }
      }, { threshold: 0.4 });
      o.observe(el);
      observers.push(o);
    };
    // Once per page view each (this runs after every render, while the sections may still be loading).
    if (!state.current.sawTickets) watch(ticketsRef.current, () => {
      state.current.sawTickets = true;
      track("ticket_drawer_opened", { event_id: eventId, props: {
        lowest_available_price: event?.price_min ?? (event?.is_free ? 0 : null),
        days_until_event: startDate ? daysUntil(startDate) : null,
      } });
    });
    if (!state.current.sawMap) watch(mapRef.current, () => { state.current.sawMap = true; });
    return () => observers.forEach((o) => o.disconnect());
  });

  const onTierChange = useCallback((tier: { id: string; name: string; price: number }, quantity: number) => {
    if (!eventId) return;
    track("ticket_tier_selected", { event_id: eventId,
      props: { tier_id: tier.id, tier_name: tier.name, unit_price: tier.price, quantity } });
  }, [eventId]);

  /** The payment window was closed without paying. */
  const onPaymentClosed = useCallback(() => {
    if (!eventId) return;
    state.current.abandoned = true;
    const { value, count } = state.current.cart;
    track("checkout_abandoned", { event_id: eventId, props: { step: "payment", cart_value: value, ticket_count: count } });
  }, [eventId]);

  const onShared = useCallback((channel: string) => {
    if (eventId) track("event_shared", { event_id: eventId, props: { share_channel: channel } });
  }, [eventId]);

  return { ticketsRef, mapRef, onTierChange, onPaymentClosed, onShared };
}
