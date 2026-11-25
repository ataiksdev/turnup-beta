"use client";
/** Event page pieces: Add to calendar, who's going, and the viewer's own ticket. */
import { useQuery } from "@tanstack/react-query";
import { Capacitor } from "@capacitor/core";
import { CalendarPlus, ChevronRight, Ticket } from "lucide-react";
import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useRef, useState } from "react";
import { Avatar } from "@/components/ui/Avatar";
import { eventsApi, organizerApi } from "@/lib/api";
import { publicOrigin, routes } from "@/lib/routes";
import { useAuthStore } from "@/store/auth";
import type { Event } from "@/types";

// ── Add to calendar ─────────────────────────────────────────────────────────────

/** 2026-11-25T18:00:00Z -> 20261125T180000Z (calendar files and Google want UTC like this). */
function calStamp(iso: string): string {
  return new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

function where(event: Event): string {
  return event.event_type === "virtual"
    ? "Online"
    : [event.venue_name, event.address, event.city].filter(Boolean).join(", ");
}

function googleCalendarUrl(event: Event, url: string): string {
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: event.title,
    dates: `${calStamp(event.start_date)}/${calStamp(event.end_date || event.start_date)}`,
    details: `${url}\n\n${(event.description ?? "").slice(0, 1500)}`,
    location: where(event),
  });
  return `https://calendar.google.com/calendar/render?${params}`;
}

/** RFC 5545 text: escape \ ; , and newlines, and fold lines longer than 75 octets. */
function icsText(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}
function fold(line: string): string {
  const out: string[] = [];
  for (let i = 0; i < line.length; i += 73) out.push((i ? " " : "") + line.slice(i, i + 73));
  return out.join("\r\n");
}

function icsFile(event: Event, url: string): string {
  const lines = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Turnup//Events//EN", "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT",
    `UID:${event.id}@turnup`,
    `DTSTAMP:${calStamp(new Date().toISOString())}`,
    `DTSTART:${calStamp(event.start_date)}`,
    `DTEND:${calStamp(event.end_date || event.start_date)}`,
    `SUMMARY:${icsText(event.title)}`,
    `DESCRIPTION:${icsText(`${url}\n\n${(event.description ?? "").slice(0, 1500)}`)}`,
    `LOCATION:${icsText(where(event))}`,
    `URL:${url}`,
    "END:VEVENT", "END:VCALENDAR",
  ];
  return lines.map(fold).join("\r\n") + "\r\n";
}

export function AddToCalendar({ event }: { event: Event }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const url = `${publicOrigin()}${routes.event(event.slug || event.id)}`;
  // A downloaded .ics file goes nowhere useful inside the Android app's web view.
  const canDownload = typeof window !== "undefined" && !Capacitor.isNativePlatform();

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);

  function download() {
    const blob = new Blob([icsFile(event, url)], { type: "text/calendar;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(event.slug || "event").slice(0, 60)}.ics`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    setOpen(false);
  }

  return (
    <div ref={ref} className="relative inline-block">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu"
        className="inline-flex items-center gap-1 text-xs font-bold text-primary hover:underline">
        <CalendarPlus size={13} aria-hidden /> Add to calendar
      </button>
      {open && (
        <div role="menu" className="absolute left-0 top-full mt-1 z-30 min-w-[200px] rounded border-2 border-border bg-bg-card shadow-brutal-sm py-1">
          <a role="menuitem" href={googleCalendarUrl(event, url)} target="_blank" rel="noopener noreferrer"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 text-sm text-text hover:bg-bg-elevated">Google Calendar</a>
          {canDownload && (
            <button role="menuitem" type="button" onClick={download}
              className="block w-full text-left px-3 py-2 text-sm text-text hover:bg-bg-elevated">
              Apple / Outlook (.ics)
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Who's going ─────────────────────────────────────────────────────────────────

export function GoingAvatars({ eventId, goingCount, interestedCount }: {
  eventId: string; goingCount: number; interestedCount: number;
}) {
  const { data } = useQuery({
    queryKey: ["attendees", eventId, "going"],
    queryFn: () => eventsApi.attendees(eventId, "going", 8),
    enabled: !!eventId && goingCount > 0,
    staleTime: 60_000,
  });
  const people = (data ?? []).filter((a) => a.user).slice(0, 6);
  const names = people.slice(0, 2).map((a) => a.user.display_name || a.user.full_name || a.user.username);
  const others = goingCount - names.length;

  return (
    <div className="flex items-center gap-3">
      {people.length > 0 && (
        <div className="flex -space-x-2 shrink-0" aria-hidden>
          {people.map((a) => (
            <Avatar key={a.user.id} src={a.user.avatar_url}
              name={a.user.display_name || a.user.full_name || a.user.username} size="xs"
              className="ring-2 ring-bg rounded-full" />
          ))}
        </div>
      )}
      <p className="text-sm text-text-secondary">
        {goingCount === 0 ? (
          <>Be the first to go</>
        ) : names.length > 0 ? (
          <>
            <strong className="text-text">{names.join(", ")}</strong>
            {others > 0 && <> and <strong className="text-text">{others.toLocaleString()}</strong> other{others !== 1 ? "s" : ""}</>}
            {" "}going
          </>
        ) : (
          <><strong className="text-text">{goingCount.toLocaleString()}</strong> going</>
        )}
        {interestedCount > 0 && <> · {interestedCount.toLocaleString()} interested</>}
      </p>
    </div>
  );
}

// ── Your ticket ─────────────────────────────────────────────────────────────────

/** The viewer's confirmed tickets for this event, with the door QR code. */
export function YourTicket({ eventId }: { eventId: string }) {
  const { token, user } = useAuthStore();
  const { data } = useQuery({
    queryKey: ["my-tickets", user?.id],
    queryFn: () => organizerApi.myTickets(token!),
    enabled: !!token && !!eventId,
  });
  const mine = (data ?? []).filter((o) => o.event_id === eventId && o.status === "confirmed" && o.ticket_code);
  if (mine.length === 0) return null;
  const first = mine[0];
  const count = mine.reduce((n, o) => n + o.quantity, 0);
  const qr = JSON.stringify({ code: first.ticket_code, order: first.id, event: first.event_id });

  return (
    <section aria-label="Your ticket" className="rounded border-2 border-success/50 bg-success/5 p-3">
      <div className="flex items-center gap-3">
        <div className="p-1.5 bg-white rounded shrink-0">
          <QRCodeSVG value={qr} size={72} level="M" includeMargin={false} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-black uppercase tracking-widest text-success">You&apos;re going</p>
          <p className="text-sm font-bold text-text truncate">
            {mine.map((o) => `${o.tier_name}${o.quantity > 1 ? ` × ${o.quantity}` : ""}`).join(", ")}
          </p>
          <p className="text-xs text-text-muted">
            {count} ticket{count !== 1 ? "s" : ""} · show the QR code at the door
          </p>
        </div>
      </div>
      <div className="flex gap-2 mt-3">
        {mine.map((o, i) => (
          <Link key={o.id} href={routes.ticket(o.id)}
            className="flex-1 flex items-center justify-center gap-1 h-9 rounded border-2 border-border bg-bg-card text-xs font-bold text-text hover:border-primary">
            <Ticket size={13} aria-hidden /> {mine.length > 1 ? `Ticket ${i + 1}` : "Open ticket"} <ChevronRight size={13} aria-hidden />
          </Link>
        )).slice(0, 3)}
      </div>
    </section>
  );
}

// ── Action bar spacing ──────────────────────────────────────────────────────────

/** Rendered while a fixed action bar is showing: tells other bottom overlays (the storage
 *  notice) to sit above it instead of covering it. */
export function ActionBarSpace() {
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--action-bar-height", "4.5rem");
    return () => { root.style.removeProperty("--action-bar-height"); };
  }, []);
  return null;
}
