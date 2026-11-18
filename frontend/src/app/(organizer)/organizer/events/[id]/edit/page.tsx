import { Suspense } from "react";
import EditEventPageClient from "./EditEventPageClient";

export const revalidate = 0;
export function generateStaticParams() { return []; }

export default function Page() {
  return <Suspense><EditEventPageClient /></Suspense>;
}
