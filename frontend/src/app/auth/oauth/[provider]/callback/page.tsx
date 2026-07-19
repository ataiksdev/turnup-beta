import { Suspense } from "react";
import OAuthCallbackPageClient from "./OAuthCallbackPageClient";

export const revalidate = 0;
export function generateStaticParams() { return []; }

export default function Page() {
  return (
    <Suspense>
      <OAuthCallbackPageClient />
    </Suspense>
  );
}
