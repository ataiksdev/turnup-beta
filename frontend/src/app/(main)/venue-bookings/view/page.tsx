import { Suspense } from "react";
import { BookingClient } from "../[id]/BookingClient";

// Static twin for the Capacitor build (?id=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><BookingClient /></Suspense>;
}
