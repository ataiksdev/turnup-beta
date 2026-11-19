import { Suspense } from "react";
import { VenueDetailClient } from "../[slug]/VenueDetailClient";

// Static twin of /venues/[slug] for the Capacitor build (?slug=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><VenueDetailClient /></Suspense>;
}
