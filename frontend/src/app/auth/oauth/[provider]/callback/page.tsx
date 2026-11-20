import { Suspense } from "react";
import OAuthCallbackPageClient from "./OAuthCallbackPageClient";
import { staticParams } from "@/lib/staticParams";

export const revalidate = 0;
export function generateStaticParams() {
  return staticParams("provider");
}

export default function Page() {
  return (
    <Suspense>
      <OAuthCallbackPageClient />
    </Suspense>
  );
}
