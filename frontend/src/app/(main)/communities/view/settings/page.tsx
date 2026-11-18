import { Suspense } from "react";
import CommunitySettingsPageClient from "../../[slug]/settings/CommunitySettingsPageClient";

// Static twin of /communities/[slug]/settings, used by the Capacitor (Android) build, where pages are static files
// and the slug comes from the query string (?slug=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><CommunitySettingsPageClient /></Suspense>;
}
