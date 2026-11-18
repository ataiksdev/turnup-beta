import { Suspense } from "react";
import EventAnalyticsPageClient from "./EventAnalyticsPageClient";

export const revalidate = 0;
export function generateStaticParams() { return []; }

export default function Page() {
  return <Suspense><EventAnalyticsPageClient /></Suspense>;
}
