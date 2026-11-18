import { Suspense } from "react";
import SeriesDetailPageClient from "./SeriesDetailPageClient";

export const revalidate = 0;
export function generateStaticParams() { return []; }

export default function Page() {
  return <Suspense><SeriesDetailPageClient /></Suspense>;
}
