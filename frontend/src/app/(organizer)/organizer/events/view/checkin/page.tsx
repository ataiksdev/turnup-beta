import { Suspense } from "react";
import CheckInPageClient from "../../[id]/checkin/CheckInPageClient";

// Static twin of /organizer/events/[id]/checkin, used by the Capacitor (Android) build, where pages are static files
// and the id comes from the query string (?id=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><CheckInPageClient /></Suspense>;
}
