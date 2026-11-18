import { Suspense } from "react";
import EditEventPageClient from "../../[id]/edit/EditEventPageClient";

// Static twin of /organizer/events/[id]/edit, used by the Capacitor (Android) build, where pages are static files
// and the id comes from the query string (?id=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><EditEventPageClient /></Suspense>;
}
