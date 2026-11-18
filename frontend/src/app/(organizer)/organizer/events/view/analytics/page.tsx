import { Suspense } from "react";
import EventAnalyticsPageClient from "../../[id]/analytics/EventAnalyticsPageClient";

// Static twin of /organizer/events/[id]/analytics, used by the Capacitor (Android) build, where pages are static files
// and the id comes from the query string (?id=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><EventAnalyticsPageClient /></Suspense>;
}
