import { Suspense } from "react";
import CoHostsPageClient from "../../[id]/cohosts/CoHostsPageClient";

// Static twin of /organizer/events/[id]/cohosts, used by the Capacitor (Android) build, where pages are static files
// and the id comes from the query string (?id=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><CoHostsPageClient /></Suspense>;
}
