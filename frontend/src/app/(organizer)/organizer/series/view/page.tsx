import { Suspense } from "react";
import SeriesDetailPageClient from "../[id]/SeriesDetailPageClient";

// Static twin of /organizer/series/[id], used by the Capacitor (Android) build, where pages are static files
// and the id comes from the query string (?id=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><SeriesDetailPageClient /></Suspense>;
}
