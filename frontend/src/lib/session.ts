"use client";
import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { User } from "@/types";

export function homeFor(user: User): string {
  return user.role === "admin" ? "/admin"
    : user.role === "moderator" ? "/admin/events/new"
    : user.role === "organizer" ? "/organizer/dashboard"
    : "/";
}

/** Store a fresh access token, load the user, and send them to their home screen. Shared by
 *  every sign-in path (password, 2FA, phone, magic link, OAuth) so they all behave the same. */
export function useFinishLogin() {
  const router = useRouter();
  const { setAuth } = useAuthStore();
  return useCallback(async (accessToken: string, redirectTo?: string) => {
    const user = await authApi.me(accessToken);
    setAuth(accessToken, user);
    // Only same-app paths: "?next=https://evil.example" or "//evil.example" must not
    // turn the login page into an open redirect.
    const safe = redirectTo && redirectTo.startsWith("/") && !redirectTo.startsWith("//")
      && !redirectTo.startsWith("/\\") ? redirectTo : undefined;
    router.replace(safe ?? homeFor(user));
  }, [router, setAuth]);
}

/** Ends the session on the server too (not just in this browser), so a copied or stolen
 *  token stops working the moment the user logs out. */
export function useLogout() {
  const router = useRouter();
  const { token, logout } = useAuthStore();
  return useCallback(async () => {
    if (token) {
      try { await authApi.logout(token); } catch { /* already invalid; clear locally anyway */ }
    }
    logout();
    router.replace("/login");
  }, [token, logout, router]);
}

// ── OAuth CSRF protection ──────────────────────────────────────────────────────
// The provider echoes back the `state` we sent. Remembering it in this tab and requiring a
// match on the callback stops "login CSRF": an attacker tricking a victim's browser into
// finishing the attacker's OAuth login (so the victim unknowingly uses the attacker's account).
const OAUTH_STATE_KEY = "turnup-oauth-state";

export function startOAuthRedirect(url: string) {
  try {
    const state = new URL(url).searchParams.get("state");
    if (state) sessionStorage.setItem(OAUTH_STATE_KEY, state);
  } catch { /* malformed URL: the callback check will fail closed */ }
  window.location.href = url;
}

export function consumeOAuthState(returned: string | null): boolean {
  let expected: string | null = null;
  try {
    expected = sessionStorage.getItem(OAUTH_STATE_KEY);
    sessionStorage.removeItem(OAUTH_STATE_KEY);
  } catch { /* storage unavailable */ }
  return !!expected && !!returned && expected === returned;
}
