"use client";
import { useAuthStore } from "@/store/auth";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { routes } from "@/lib/routes";

// Redirect /profile → /profile/:username.
// Uses router.replace() (not next/navigation's redirect(), which only works during
// Server Component rendering — calling it from a Client Component effect throws
// outside the render phase and can misbehave instead of navigating cleanly).
export default function ProfileRedirect() {
  const { user, hasHydrated } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (!hasHydrated) return;
    if (user?.username) {
      router.replace(routes.profile(user.username));
    } else {
      router.replace("/login");
    }
  }, [hasHydrated, user, router]);

  return null;
}
