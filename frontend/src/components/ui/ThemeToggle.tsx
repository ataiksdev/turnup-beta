"use client";
import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { resolveMode } from "@/lib/themes";
import { useThemeChoice } from "@/lib/useThemeChoice";
import { cn } from "@/lib/utils";

/** Quick light/dark switch for the current theme. Full theme choice is in Settings ->
 *  Appearance. (Applying the theme to the page is ThemeController's job.) */
export function ThemeToggle({ className }: { className?: string }) {
  const { mode, choose } = useThemeChoice();
  // Resolve "system" only after mount: the server can't know the device's preference.
  const [isDark, setIsDark] = useState(true);
  useEffect(() => { setIsDark(resolveMode(mode) === "dark"); }, [mode]);

  return (
    <button
      onClick={() => choose({ mode: isDark ? "light" : "dark" })}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={isDark}
      className={cn(
        "p-2 rounded border border-border-subtle hover:bg-bg-elevated hover:border-border transition-all duration-100",
        className,
      )}
    >
      {isDark
        ? <Sun  size={18} className="text-text-secondary" aria-hidden />
        : <Moon size={18} className="text-text-secondary" aria-hidden />}
    </button>
  );
}
