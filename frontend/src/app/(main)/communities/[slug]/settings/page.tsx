import { Suspense } from "react";
import CommunitySettingsPageClient from "./CommunitySettingsPageClient";
import { staticParams } from "@/lib/staticParams";

export const revalidate = 0;
export function generateStaticParams() {
  return staticParams("slug");
}

export default function Page() {
  return <Suspense><CommunitySettingsPageClient /></Suspense>;
}
