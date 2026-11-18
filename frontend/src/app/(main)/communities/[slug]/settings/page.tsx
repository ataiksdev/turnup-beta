import { Suspense } from "react";
import CommunitySettingsPageClient from "./CommunitySettingsPageClient";

export const revalidate = 0;
export function generateStaticParams() { return []; }

export default function Page() {
  return <Suspense><CommunitySettingsPageClient /></Suspense>;
}
