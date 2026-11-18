import { Suspense } from "react";
import TicketDetailPageClient from "../[id]/TicketDetailPageClient";

// Static twin of /tickets/[id], used by the Capacitor (Android) build, where pages are static files
// and the id comes from the query string (?id=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><TicketDetailPageClient /></Suspense>;
}
