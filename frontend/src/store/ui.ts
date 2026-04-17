"use client";
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

type Theme = "dark" | "light";

interface UIState {
  searchOpen: boolean;
  theme: Theme;
  setSearchOpen: (v: boolean) => void;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      searchOpen: false,
      theme: "dark",
      setSearchOpen: (v) => set({ searchOpen: v }),
      setTheme: (t) => set({ theme: t }),
      toggleTheme: () => set({ theme: get().theme === "dark" ? "light" : "dark" }),
    }),
    {
      name: "turnup-ui",
      storage: createJSONStorage(() => {
        // SSR safety
        if (typeof window === "undefined") return { getItem: () => null, setItem: () => {}, removeItem: () => {} };
        return localStorage;
      }),
      partialize: (s) => ({ theme: s.theme }),
    },
  ),
);
