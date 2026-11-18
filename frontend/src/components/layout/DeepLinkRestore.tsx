"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { STATIC_EXPORT } from "@/lib/routes";

/**
 * Android app only. Capacitor's local server answers a full page load of any path without a
 * file extension (e.g. /events/view?id=abc after Android restores the app) with the root
 * index.html, i.e. this home page, while the address stays /events/view?id=abc. Rendered on
 * the home page, this notices the mismatch and client-side navigates to the screen the
 * address names, the same way an in-app link would.
 */
export function DeepLinkRestore() {
  const router = useRouter();
  useEffect(() => {
    if (!STATIC_EXPORT) return;
    const { pathname, search } = window.location;
    if (pathname !== "/" && pathname !== "/index.html") router.replace(pathname + search);
  }, [router]);
  return null;
}
