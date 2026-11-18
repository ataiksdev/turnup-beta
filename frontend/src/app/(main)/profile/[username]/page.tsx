import { Suspense } from "react";
import ProfilePageClient from "./ProfilePageClient";

export const revalidate = 0;
export function generateStaticParams() { return []; }

export default function Page() {
  return <Suspense><ProfilePageClient /></Suspense>;
}
