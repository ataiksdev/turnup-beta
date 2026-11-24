"use client";
import { useEffect } from "react";
import { setTrackingAuth, startTracking } from "@/lib/track";
import { useAuthStore } from "@/store/auth";

/** Starts activity tracking (lib/track.ts) and keeps it in step with who's signed in. */
export function TrackingProvider() {
  const token = useAuthStore((s) => s.token);
  const city = useAuthStore((s) => s.user?.city ?? null);
  const consent = useAuthStore((s) => !!s.user?.profiling_consent);
  const hydrated = useAuthStore((s) => s.hasHydrated);

  useEffect(() => startTracking(), []);
  useEffect(() => {
    if (hydrated) setTrackingAuth({ token, city, profilingConsent: consent });
  }, [hydrated, token, city, consent]);
  return null;
}
