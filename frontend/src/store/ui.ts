"use client";
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import {
  DEFAULT_MODE, DEFAULT_THEME, isModePreference, isThemeId, resolveMode,
  type ModePreference, type ThemeId, type ThemeMode,
} from "@/lib/themes";

interface UIState {
  searchOpen: boolean;
  /** Which theme (colour palette + style). */
  palette: ThemeId;
  /** light | dark | system (follow the phone/computer). */
  mode: ModePreference;
  setSearchOpen: (v: boolean) => void;
  setPalette: (p: ThemeId) => void;
  setMode: (m: ModePreference) => void;
  /** The account's theme_preference as this device last saw it. The account's theme is
   *  adopted only when it differs from this (i.e. it changed on another device, or a
   *  different account signed in), so a local choice is never overwritten by stale data. */
  seenAccountTheme: string | null;
  setSeenAccountTheme: (v: string | null) => void;
  /** Sun/moon button: flips between light and dark (from "system" too). */
  toggleMode: () => void;
  /** @deprecated kept for older callers: the resolved light/dark mode. */
  theme: ThemeMode;
  /** @deprecated use toggleMode */
  toggleTheme: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      searchOpen: false,
      palette: DEFAULT_THEME,
      mode: DEFAULT_MODE,
      theme: "dark",
      seenAccountTheme: null,
      setSeenAccountTheme: (seenAccountTheme) => set({ seenAccountTheme }),
      setSearchOpen: (v) => set({ searchOpen: v }),
      setPalette: (palette) => set({ palette }),
      setMode: (mode) => set({ mode, theme: resolveMode(mode) }),
      toggleMode: () => {
        const next: ThemeMode = resolveMode(get().mode) === "dark" ? "light" : "dark";
        set({ mode: next, theme: next });
      },
      toggleTheme: () => get().toggleMode(),
    }),
    {
      name: "turnup-ui",
      version: 2,
      storage: createJSONStorage(() => {
        // SSR safety
        if (typeof window === "undefined") return { getItem: () => null, setItem: () => {}, removeItem: () => {} };
        return localStorage;
      }),
      partialize: (s) => ({ palette: s.palette, mode: s.mode, seenAccountTheme: s.seenAccountTheme }),
      // v0 stored only { theme: "dark" | "light" }: keep that choice on the default palette.
      // v2 removed the Lagoon, Palm and Neon Night themes: anyone on one moves to the default.
      migrate: (persisted, version) => {
        const old = (persisted ?? {}) as { theme?: unknown; palette?: unknown; mode?: unknown };
        if (version === 0) {
          return { palette: DEFAULT_THEME, mode: isModePreference(old.theme) ? old.theme : DEFAULT_MODE };
        }
        return {
          palette: isThemeId(old.palette) ? old.palette : DEFAULT_THEME,
          mode: isModePreference(old.mode) ? old.mode : DEFAULT_MODE,
          seenAccountTheme: typeof (old as { seenAccountTheme?: unknown }).seenAccountTheme === "string"
            ? (old as { seenAccountTheme: string }).seenAccountTheme : null,
        };
      },
      onRehydrateStorage: () => (state) => {
        if (state) state.theme = resolveMode(state.mode);
      },
    },
  ),
);
