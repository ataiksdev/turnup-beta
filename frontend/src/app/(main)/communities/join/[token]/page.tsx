import { Suspense } from "react";
import JoinViaInvitePageClient from "./JoinViaInvitePageClient";
import { staticParams } from "@/lib/staticParams";

export const revalidate = 0;
export function generateStaticParams() {
  return staticParams("token");
}

export default function Page() {
  return <Suspense><JoinViaInvitePageClient /></Suspense>;
}
