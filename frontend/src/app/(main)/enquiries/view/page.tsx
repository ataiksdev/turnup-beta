import { Suspense } from "react";
import { EnquiryClient } from "../[id]/EnquiryClient";

// Static twin for the Capacitor build (?id=...). See lib/routes.ts.
export default function Page() {
  return <Suspense><EnquiryClient /></Suspense>;
}
