"use client";
import { useEffect } from "react";
import { authApi } from "@/lib/api";
import { applyTheme, decodePreference, encodePreference } from "@/lib/themes";
import { useAuthStore } from "@/store/auth";
import { useUIStore } from "@/store/ui";

/** Keeps the page's theme in step with the user's choice. Mounted once, in Providers.
 *  - applies palette + mode whenever they change (the <head> boot script covers first paint);
 *  - in "system" mode, follows the phone/computer switching between light and dark;
 *  - adopts the theme saved on the account when it changed elsewhere (another device, or a
 *    different account signing in), or saves this device's theme to an account with none. */
export function ThemeController() {
  const palette = useUIStore((s) => s.palette);
  const mode = useUIStore((s) => s.mode);
  const { user, token, setUser } = useAuthStore();

  useEffect(() => { applyTheme(palette, mode); }, [palette, mode]);

  useEffect(() => {
    if (mode !== "system" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme(palette, "system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [palette, mode]);

  // The signed-in user is cached in localStorage: refresh it once per session so a theme
  // chosen on another device (and any other account changes) arrive here.
  useEffect(() => {
    if (token) authApi.me(token).then(setUser).catch(() => { /* 401 handled globally */ });
  }, [token, setUser]);

  const accountTheme = user?.theme_preference ?? null;
  useEffect(() => {
    if (!user) return;
    const ui = useUIStore.getState();
    if (accountTheme === ui.seenAccountTheme) return; // nothing new from the account
    const saved = decodePreference(accountTheme);
    if (saved) {
      if (ui.palette !== saved.theme) ui.setPalette(saved.theme);
      if (ui.mode !== saved.mode) ui.setMode(saved.mode);
      ui.setSeenAccountTheme(accountTheme);
    } else if (token) {
      // Account has no theme yet: keep this device's and save it to the account.
      authApi.updateMe(token, { theme_preference: encodePreference(ui.palette, ui.mode) })
        .then((u) => { useUIStore.getState().setSeenAccountTheme(u.theme_preference ?? null); setUser(u); })
        .catch(() => {});
    }
  }, [user, accountTheme, token, setUser]);

  return null;
}
