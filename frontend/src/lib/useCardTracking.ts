"use client";
import { useCallback, useEffect, useRef } from "react";
import { rememberClick, track } from "@/lib/track";
import type { Event } from "@/types";

/** Where a card is shown. Cards without one aren't tracked (impressions and clicks). */
export interface CardTracking {
  /** Which feed: for_you, trending, featured, following, search, discover... */
  surface: string;
  /** 0-based position in that feed. */
  position: number;
}

/**
 * Impression: the card was at least half on screen for a second (counted once per card per
 * feed load). Click: tapped, with its position and the feed's rec_request_id, remembered so
 * the event page can say where the view came from.
 */
export function useCardTracking<T extends HTMLElement>(event: Event, where?: CardTracking) {
  const ref = useRef<T | null>(null);
  const seen = useRef(false);
  const surface = where?.surface;
  const position = where?.position;
  const recId = event.rec_request_id ?? null;

  useEffect(() => {
    seen.current = false;
  }, [recId, event.id]);

  useEffect(() => {
    const el = ref.current;
    if (!el || surface === undefined || typeof IntersectionObserver === "undefined") return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !seen.current) {
        timer = setTimeout(() => {
          seen.current = true;
          track("feed_impression", {
            event_id: event.id, surface, position, rec_request_id: recId,
            is_promoted: !!event.is_featured,
          });
          observer.disconnect();
        }, 1000);
      } else if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    }, { threshold: 0.5 });
    observer.observe(el);
    return () => { observer.disconnect(); if (timer) clearTimeout(timer); };
  }, [event.id, event.is_featured, surface, position, recId]);

  const onClick = useCallback(() => {
    if (surface === undefined) return;
    track("event_clicked", { event_id: event.id, surface, position, rec_request_id: recId,
                             is_promoted: !!event.is_featured });
    rememberClick({ event_id: event.id, surface, position, rec_request_id: recId });
  }, [event.id, event.is_featured, surface, position, recId]);

  return { ref, onClick };
}
