import { Suspense } from "react";
import { EventDetailClient } from "../[id]/EventDetailClient";

// Static twin of /events/[id], used by the Capacitor (Android) build, where pages are static files
// and the id comes from the query string (?id=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><EventDetailClient /></Suspense>;
}
