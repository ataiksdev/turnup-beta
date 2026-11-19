"use client";
import { useCallback } from "react";
import { authApi } from "@/lib/api";
import { encodePreference, type ModePreference, type ThemeId } from "@/lib/themes";
import { useAuthStore } from "@/store/auth";
import { useUIStore } from "@/store/ui";

/** Change the theme and, when signed in, save it to the account so it follows the user to
 *  their other devices. The change applies instantly; saving happens in the background. */
export function useThemeChoice() {
  const { palette, mode, setPalette, setMode } = useUIStore();
  const { token, setUser } = useAuthStore();

  const choose = useCallback((next: { palette?: ThemeId; mode?: ModePreference }) => {
    const p = next.palette ?? useUIStore.getState().palette;
    const m = next.mode ?? useUIStore.getState().mode;
    if (next.palette) setPalette(p);
    if (next.mode) setMode(m);
    if (token) {
      authApi.updateMe(token, { theme_preference: encodePreference(p, m) })
        .then((u) => {
          useUIStore.getState().setSeenAccountTheme(u.theme_preference ?? null);
          setUser(u);
        })
        .catch(() => { /* offline: the local choice still applies; it syncs next change */ });
    }
  }, [token, setPalette, setMode, setUser]);

  return { palette, mode, choose };
}
