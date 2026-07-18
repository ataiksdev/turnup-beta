"use client";
import { useQuery } from "@tanstack/react-query";
import { organizerApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { Ticket, CheckCircle2, Clock, XCircle, CalendarDays, MapPin } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, { icon: typeof CheckCircle2; label: string; cls: string }> = {
  confirmed: { icon: CheckCircle2, label: "Confirmed",  cls: "text-success bg-success/10 border-success/30" },
  pending:   { icon: Clock,        label: "Pending",    cls: "text-info bg-info/10 border-info/30" },
  cancelled: { icon: XCircle,      label: "Cancelled",  cls: "text-error bg-error/10 border-error/30" },
  refunded:  { icon: XCircle,      label: "Refunded",   cls: "text-text-muted bg-bg-elevated border-border" },
};

export default function TicketsPage() {
  const { token, user } = useAuthStore();

  const { data: tickets, isLoading, isError } = useQuery({
    queryKey: ["my-tickets", user?.id],
    queryFn: () => organizerApi.myTickets(token!),
    enabled: !!token,
  });

  if (!user || !token) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4 px-8 text-center">
        <Ticket size={48} className="text-primary" aria-hidden />
        <h2 className="text-xl font-black text-text">Your tickets</h2>
        <p className="text-sm text-text-secondary">Log in to see your purchased tickets.</p>
        <Link href="/login"><Button fullWidth>Log In</Button></Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="My Tickets" />

      <div className="px-4 pt-4 space-y-3">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))
        ) : isError ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
            <Ticket size={40} className="text-border-strong" aria-hidden />
            <p className="text-text-secondary font-medium">Could not load tickets</p>
            <p className="text-sm text-text-muted">Check your connection and try again</p>
          </div>
        ) : tickets && tickets.length > 0 ? (
          tickets.map((t) => {
            const s = STATUS_STYLES[t.status] ?? STATUS_STYLES.confirmed;
            const StatusIcon = s.icon;
            const eventDate = t.event_date
              ? new Date(t.event_date).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })
              : null;

            return (
              <div key={t.id} className="bg-bg-card border-2 border-border rounded shadow-brutal-sm overflow-hidden">
                {/* Cover strip */}
                {t.event_cover && (
                  <div className="h-20 w-full overflow-hidden">
                    <img src={t.event_cover} alt="" className="w-full h-full object-cover" />
                  </div>
                )}

                <div className="p-3 space-y-2">
                  {/* Event title */}
                  {t.event_slug ? (
                    <Link href={`/events/${t.event_slug}`} className="font-black text-text text-sm hover:text-primary transition-colors line-clamp-1">
                      {t.event_title ?? "Event"}
                    </Link>
                  ) : (
                    <p className="font-black text-text text-sm line-clamp-1">{t.event_title ?? "Event"}</p>
                  )}

                  <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-text-muted">
                    {eventDate && (
                      <span className="flex items-center gap-1">
                        <CalendarDays size={11} /> {eventDate}
                      </span>
                    )}
                    {t.event_city && (
                      <span className="flex items-center gap-1">
                        <MapPin size={11} /> {t.event_city}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-1 border-t border-border">
                    <div>
                      <p className="text-xs text-text-muted">{t.tier_name} × {t.quantity}</p>
                      <p className="font-black text-text text-sm">
                        {t.unit_price === 0 ? "Free" : `₦${t.total_price.toLocaleString()}`}
                      </p>
                    </div>
                    <span className={cn(
                      "flex items-center gap-1 px-2 py-1 rounded border text-[10px] font-black uppercase tracking-widest",
                      s.cls,
                    )}>
                      <StatusIcon size={11} aria-hidden /> {s.label}
                    </span>
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
            <Ticket size={40} className="text-border-strong" aria-hidden />
            <p className="text-text-secondary font-medium">No tickets yet</p>
            <p className="text-sm text-text-muted">Tickets you purchase will appear here</p>
            <Link href="/search"><Button variant="secondary" size="sm">Browse Events</Button></Link>
          </div>
        )}
      </div>
    </div>
  );
}
