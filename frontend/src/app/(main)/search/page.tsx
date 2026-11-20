"use client";
import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

/** Search is now part of /discover: forward there, keeping any filters in the address. */
function Forward() {
  const router = useRouter();
  const params = useSearchParams();
  useEffect(() => {
    const q = params.toString();
    router.replace(q ? `/discover?${q}` : "/discover");
  }, [router, params]);
  return null;
}

export default function Page() {
  return <Suspense><Forward /></Suspense>;
}
