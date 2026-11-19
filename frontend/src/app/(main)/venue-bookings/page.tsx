"use client";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import Link from "next/link";
import { TopBar } from "@/components/layout/TopBar";
import { BOOKING_STATUS, bookingsApi, naira } from "@/lib/marketplace";
import { routes } from "@/lib/routes";
import { useAuthStore } from "@/store/auth";

export default function VenueBookingsPage() {
  const { token, hasHydrated } = useAuthStore();
  const { data, isPending } = useQuery({
    queryKey: ["venue-bookings", !!token], queryFn: () => bookingsApi.bookings(token!), enabled: hasHydrated && !!token,
  });
  return (
    <div className="pb-24">
      <TopBar title="Venue bookings" back />
      <div className="px-4 py-4 space-y-2">
        <div className="flex gap-2 text-xs font-bold">
          <Link href="/enquiries" className="px-2.5 py-1 rounded border-2 border-border text-text-secondary">Enquiries</Link>
          <span className="px-2.5 py-1 rounded bg-text text-bg">Bookings</span>
        </div>
        {isPending && token && <div className="h-20 rounded border-2 border-border bg-bg-card animate-pulse" />}
        {data?.length === 0 && <p className="text-sm text-text-muted">No venue bookings yet.</p>}
        {data?.map((b) => (
          <Link key={b.id} href={routes.venueBooking(b.id)}
            className="block p-3 rounded border-2 border-border bg-bg-card hover:border-primary space-y-0.5">
            <div className="flex justify-between gap-2">
              <p className="text-sm font-bold text-text">{b.venue.name}</p>
              <span className="text-[10px] font-black uppercase text-text-secondary">{BOOKING_STATUS[b.status] ?? b.status}</span>
            </div>
            <p className="text-xs text-text-muted">{format(new Date(b.starts_at), "EEE d MMM yyyy, h:mm a")} · {b.space.name}</p>
            <p className="text-xs text-text-secondary">Paid {naira(b.paid_kobo)} of {naira(b.total_kobo)}
              {b.balance_kobo > 0 && ["confirmed"].includes(b.status) && ` · balance due ${format(new Date(b.balance_due_at), "d MMM")}`}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
