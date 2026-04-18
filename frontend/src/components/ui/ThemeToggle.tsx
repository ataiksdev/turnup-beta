"use client";
import { Moon, Sun } from "lucide-react";
import { useEffect } from "react";
import { useUIStore } from "@/store/ui";
import { cn } from "@/lib/utils";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggleTheme } = useUIStore();

  // Sync class on html element whenever theme changes
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("light", theme === "light");
    root.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return (
    <button
      onClick={toggleTheme}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={theme === "dark"}
      className={cn(
        "p-2 rounded border border-border-subtle hover:bg-bg-elevated hover:border-border transition-all duration-100",
        className,
      )}
    >
      {theme === "dark"
        ? <Sun  size={18} className="text-text-secondary" aria-hidden />
        : <Moon size={18} className="text-text-secondary" aria-hidden />}
    </button>
  );
}
