import { Suspense } from "react";
import { CommunityDetailClient } from "../[slug]/CommunityDetailClient";

// Static twin of /communities/[slug], used by the Capacitor (Android) build, where pages are static files
// and the slug comes from the query string (?slug=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><CommunityDetailClient /></Suspense>;
}
