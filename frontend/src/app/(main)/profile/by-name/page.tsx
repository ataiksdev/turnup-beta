import { Suspense } from "react";
import ProfilePageClient from "../[username]/ProfilePageClient";

// Static twin of /profile/[username], used by the Capacitor (Android) build, where pages are static files
// and the username comes from the query string (?username=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><ProfilePageClient /></Suspense>;
}
