import { Suspense } from "react";
import EventAnalyticsPageClient from "./EventAnalyticsPageClient";
import { staticParams } from "@/lib/staticParams";

export const revalidate = 0;
export function generateStaticParams() {
  return staticParams("id");
}

export default function Page() {
  return <Suspense><EventAnalyticsPageClient /></Suspense>;
}
