import { Suspense } from "react";
import JoinViaInvitePageClient from "../[token]/JoinViaInvitePageClient";

// Static twin of /communities/join/[token], used by the Capacitor (Android) build, where pages are static files
// and the token comes from the query string (?token=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><JoinViaInvitePageClient /></Suspense>;
}
