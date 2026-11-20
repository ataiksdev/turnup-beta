import { Suspense } from "react";
import ProfilePageClient from "./ProfilePageClient";
import { staticParams } from "@/lib/staticParams";

export const revalidate = 0;
export function generateStaticParams() {
  return staticParams("username");
}

export default function Page() {
  return <Suspense><ProfilePageClient /></Suspense>;
}
