"use client";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { organizerApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { ShareButton } from "@/components/ui/ShareButton";
import { QRCodeSVG } from "qrcode.react";
import {
  CheckCircle2, Clock, XCircle, CalendarDays, MapPin,
  Ticket, Building2, Tag,
} from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { format } from "date-fns";

const STATUS_STYLES: Record<string, { icon: typeof CheckCircle2; label: string; cls: string }> = {
  confirmed: { icon: CheckCircle2, label: "Confirmed", cls: "text-success bg-success/10 border-success/30" },
  pending:   { icon: Clock,        label: "Pending",   cls: "text-info bg-info/10 border-info/30" },
  cancelled: { icon: XCircle,      label: "Cancelled", cls: "text-error bg-error/10 border-error/30" },
  refunded:  { icon: XCircle,      label: "Refunded",  cls: "text-text-muted bg-bg-elevated border-border" },
};

export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuthStore();

  const { data: ticket, isLoading, isError } = useQuery({
    queryKey: ["ticket", id],
    queryFn: () => organizerApi.getTicket(token!, id),
    enabled: !!token && !!id,
  });

  if (!token) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4 px-8 text-center">
        <Ticket size={48} className="text-primary" />
        <p className="text-sm text-text-secondary">Sign in to view your ticket</p>
        <Link href="/login"><Button>Log In</Button></Link>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col">
        <TopBar back title="Ticket" />
        <div className="px-4 py-6 space-y-4">
          <div className="skeleton-shimmer h-48 rounded-xl bg-bg-elevated" />
          <div className="skeleton-shimmer h-6 w-48 rounded bg-bg-elevated" />
          <div className="skeleton-shimmer h-4 w-full rounded bg-bg-elevated" />
        </div>
      </div>
    );
  }

  if (isError || !ticket) {
    return (
      <div className="flex flex-col">
        <TopBar back title="Ticket" />
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-center px-8">
          <Ticket size={40} className="text-border-strong" />
          <p className="text-sm font-black text-text-secondary uppercase tracking-wide">Ticket not found</p>
          <Link href="/tickets"><Button variant="secondary" size="sm">Back to tickets</Button></Link>
        </div>
      </div>
    );
  }

  const s = STATUS_STYLES[ticket.status] ?? STATUS_STYLES.confirmed;
  const StatusIcon = s.icon;
  const isConfirmed = ticket.status === "confirmed";
  const eventDate = ticket.event_date
    ? format(new Date(ticket.event_date), "EEE, MMM d yyyy · h:mm a")
    : null;

  // QR value encodes a JSON payload for the check-in scanner
  const qrValue = JSON.stringify({
    code: ticket.ticket_code,
    order: ticket.id,
    event: ticket.event_id,
  });

  return (
    <div className="flex flex-col pb-8">
      <TopBar back title="My Ticket" />

      {/* Cover */}
      {ticket.event_cover && (
        <div className="h-40 w-full overflow-hidden">
          <img src={ticket.event_cover} alt="" className="w-full h-full object-cover" />
        </div>
      )}

      <div className="px-4 py-5 space-y-5">
        {/* Event name + status */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {ticket.event_slug ? (
              <Link href={`/events/${ticket.event_slug}`} className="text-lg font-black text-text hover:text-primary transition-colors leading-snug">
                {ticket.event_title ?? "Event"}
              </Link>
            ) : (
              <h1 className="text-lg font-black text-text leading-snug">{ticket.event_title ?? "Event"}</h1>
            )}
          </div>
          <span className={cn(
            "shrink-0 flex items-center gap-1 px-2 py-1 rounded border text-[10px] font-black uppercase tracking-widest mt-0.5",
            s.cls,
          )}>
            <StatusIcon size={11} aria-hidden /> {s.label}
          </span>
        </div>

        {/* Event meta */}
        <div className="space-y-2 text-sm text-text-secondary">
          {eventDate && (
            <div className="flex items-center gap-2">
              <CalendarDays size={15} className="text-text-muted shrink-0" />
              <span>{eventDate}</span>
            </div>
          )}
          {ticket.event_venue && (
            <div className="flex items-center gap-2">
              <Building2 size={15} className="text-text-muted shrink-0" />
              <span>{ticket.event_venue}</span>
            </div>
          )}
          {(ticket.event_address || ticket.event_city) && (
            <div className="flex items-center gap-2">
              <MapPin size={15} className="text-text-muted shrink-0" />
              <span>{[ticket.event_address, ticket.event_city].filter(Boolean).join(", ")}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <Tag size={15} className="text-text-muted shrink-0" />
            <span>{ticket.tier_name} × {ticket.quantity}</span>
          </div>
        </div>

        {/* Ticket price block */}
        <div className="flex items-center justify-between p-3 rounded border-2 border-border bg-bg-card">
          <div>
            <p className="text-[10px] font-black text-text-muted uppercase tracking-widest">Total paid</p>
            <p className="text-xl font-black text-text mt-0.5">
              {ticket.unit_price === 0 ? "Free" : `₦${ticket.total_price.toLocaleString()}`}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] font-black text-text-muted uppercase tracking-widest">Order ID</p>
            <p className="font-mono text-xs text-text-muted mt-0.5">{ticket.id.slice(0, 8).toUpperCase()}</p>
          </div>
        </div>

        {/* QR code — only for confirmed tickets */}
        {isConfirmed && ticket.ticket_code ? (
          <div className="flex flex-col items-center gap-4 p-6 rounded-xl border-2 border-border bg-bg-card">
            <p className="text-[10px] font-black text-text-muted uppercase tracking-widest">Entry QR Code</p>
            <div className="p-4 bg-white rounded-xl shadow-brutal-sm">
              <QRCodeSVG
                value={qrValue}
                size={200}
                level="M"
                includeMargin={false}
              />
            </div>
            <p className="text-xs text-text-muted text-center">
              Show this at the door. Screenshot it for offline access.
            </p>
            <p className="font-mono text-xs text-text-muted tracking-widest">
              {ticket.ticket_code.toUpperCase().replace(/-/g, " ")}
            </p>
            {ticket.checked_in_at && (
              <div className="flex items-center gap-1.5 text-xs font-bold text-success">
                <CheckCircle2 size={14} />
                Checked in {format(new Date(ticket.checked_in_at), "MMM d · h:mm a")}
              </div>
            )}
          </div>
        ) : !isConfirmed ? (
          <div className="flex flex-col items-center gap-2 p-6 rounded-xl border-2 border-border bg-bg-card text-center">
            <Ticket size={32} className="text-text-muted" />
            <p className="text-sm text-text-muted">QR code available once your ticket is confirmed</p>
          </div>
        ) : null}

        {/* Share event */}
        {ticket.event_slug && (
          <div className="flex items-center gap-3 p-3 rounded border-2 border-border bg-bg-card">
            <div className="flex-1 min-w-0">
              <p className="text-xs font-black text-text-secondary uppercase tracking-wide">Going to this event?</p>
              <p className="text-[10px] text-text-muted mt-0.5">Share it with friends</p>
            </div>
            <ShareButton
              title={ticket.event_title ?? "Event on Turnup"}
              text={`I'm going to ${ticket.event_title} — check it out on Turnup!`}
              url={typeof window !== "undefined"
                ? `${window.location.origin}/events/${ticket.event_slug}`
                : `/events/${ticket.event_slug}`}
              size={16}
            />
          </div>
        )}

        {/* Back link */}
        <Link href="/tickets">
          <Button variant="secondary" fullWidth>← All tickets</Button>
        </Link>
      </div>
    </div>
  );
}
