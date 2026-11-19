"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { BookingsTab, CalendarTab, EnquiriesTab, MoneyTab } from "@/components/venue-portal/OpsTabs";
import { DealsTab, EventsTab, GrowTab, ReviewsTab, TeamTab } from "@/components/venue-portal/GrowTabs";
import { ListingTab, OverviewTab, VerificationTab } from "@/components/venue-portal/SetupTabs";
import { useVenue } from "@/components/venue-portal/shared";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";

const TABS = [
  ["overview", "Overview", OverviewTab], ["listing", "Listing", ListingTab], ["verification", "Verification & payouts", VerificationTab],
  ["enquiries", "Enquiries", EnquiriesTab], ["bookings", "Bookings", BookingsTab], ["calendar", "Calendar", CalendarTab],
  ["money", "Money", MoneyTab], ["events", "Events", EventsTab], ["deals", "Deals", DealsTab], ["reviews", "Reviews", ReviewsTab],
  ["team", "Team", TeamTab], ["grow", "Pro & featured", GrowTab],
] as const;

function Manage() {
  const search = useSearchParams();
  const router = useRouter();
  const id = search.get("id") ?? "";
  const tab = search.get("tab") ?? "overview";
  const { data: v, error } = useVenue(id);
  if (error) return <p className="text-sm text-text-muted">This venue isn't available to you. <Link href="/venue" className="text-primary underline">Back</Link></p>;
  if (!v) return <div className="h-40 rounded border-2 border-border bg-bg-card animate-pulse" />;
  const Current = (TABS.find(([k]) => k === tab) ?? TABS[0])[2];
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Link href="/venue" className="text-xs font-bold text-text-muted hover:text-text">Your venues</Link>
        <span className="text-text-muted">/</span>
        <h1 className="text-xl font-black text-text truncate">{v.name}</h1>
        {v.status === "live" && <Link href={routes.venue(v.slug)} className="ml-auto text-xs font-bold text-primary underline">View public page</Link>}
      </div>
      <nav className="flex gap-1 overflow-x-auto pb-1 border-b-2 border-border" aria-label="Venue sections">
        {TABS.map(([k, label]) => (
          <button key={k} onClick={() => router.replace(`/venue/manage?id=${id}&tab=${k}`)} aria-current={tab === k ? "page" : undefined}
            className={cn("shrink-0 px-3 py-2 text-xs font-bold rounded-t", tab === k ? "bg-primary text-on-primary" : "text-text-secondary hover:text-text")}>
            {label}
          </button>
        ))}
      </nav>
      <Current v={v} />
    </div>
  );
}

export default function ManageVenuePage() {
  return <Suspense><Manage /></Suspense>;
}
