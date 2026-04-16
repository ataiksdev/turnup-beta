"use client";
import { create } from "zustand";

interface UIState {
  searchOpen: boolean;
  setSearchOpen: (v: boolean) => void;
}

export const useUIStore = create<UIState>()((set) => ({
  searchOpen: false,
  setSearchOpen: (v) => set({ searchOpen: v }),
}));
