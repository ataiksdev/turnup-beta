"use client";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import Link from "next/link";
import { TopBar } from "@/components/layout/TopBar";
import { bookingsApi } from "@/lib/marketplace";
import { routes } from "@/lib/routes";
import { useAuthStore } from "@/store/auth";

export default function EnquiriesPage() {
  const { token, hasHydrated } = useAuthStore();
  const { data, isPending } = useQuery({
    queryKey: ["enquiries", !!token], queryFn: () => bookingsApi.enquiries(token!), enabled: hasHydrated && !!token,
  });
  return (
    <div className="pb-24">
      <TopBar title="Venue enquiries" back />
      <div className="px-4 py-4 space-y-2">
        <div className="flex gap-2 text-xs font-bold">
          <span className="px-2.5 py-1 rounded bg-text text-bg">Enquiries</span>
          <Link href="/venue-bookings" className="px-2.5 py-1 rounded border-2 border-border text-text-secondary">Bookings</Link>
          <Link href="/venues" className="ml-auto px-2.5 py-1 rounded border-2 border-border text-primary">Find venues</Link>
        </div>
        {!token && hasHydrated && <p className="text-sm text-text-muted">Log in to see your enquiries.</p>}
        {isPending && token && <div className="h-20 rounded border-2 border-border bg-bg-card animate-pulse" />}
        {data?.length === 0 && <p className="text-sm text-text-muted">No enquiries yet. Find a venue and send one.</p>}
        {data?.map((e) => (
          <Link key={e.id} href={routes.enquiry(e.id)}
            className="flex gap-3 p-3 rounded border-2 border-border bg-bg-card hover:border-primary">
            <div className="w-12 h-12 rounded bg-bg-elevated overflow-hidden shrink-0">
              {e.venue.cover_image && <img src={e.venue.cover_image} alt="" className="w-full h-full object-cover" />}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-bold text-text truncate">{e.venue.name}</p>
                {e.unread > 0 && <span className="px-1.5 rounded-full bg-primary text-on-primary text-[10px] font-black">{e.unread}</span>}
              </div>
              <p className="text-xs text-text-muted">{format(new Date(e.starts_at), "EEE d MMM yyyy")} · {e.guest_count} guests</p>
              <p className="text-[10px] font-black uppercase text-text-secondary">{e.status}</p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
