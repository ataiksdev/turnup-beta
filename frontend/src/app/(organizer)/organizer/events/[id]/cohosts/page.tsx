import { Suspense } from "react";
import CoHostsPageClient from "./CoHostsPageClient";

export const revalidate = 0;
export function generateStaticParams() { return []; }

export default function Page() {
  return <Suspense><CoHostsPageClient /></Suspense>;
}
