"use client";
import { Suspense } from "react";
import EventAnalyticsPageClient from "@/app/(organizer)/organizer/events/[id]/analytics/EventAnalyticsPageClient";

// Any event's analytics and insights, read-only, for admins (?id=...). The same report the
// event's host sees, minus the controls that need the host (edit, check-in, waitlist).
export default function AdminEventAnalyticsPage() {
  return <Suspense><EventAnalyticsPageClient admin /></Suspense>;
}
