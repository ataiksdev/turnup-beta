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
    root.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return (
    <button
      onClick={toggleTheme}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={theme === "dark"}
      className={cn(
        "p-2 rounded-xl hover:bg-bg-elevated transition-colors focus-visible:ring-2 focus-visible:ring-primary",
        className,
      )}
    >
      {theme === "dark"
        ? <Sun  size={18} className="text-text-secondary" aria-hidden />
        : <Moon size={18} className="text-text-secondary" aria-hidden />}
    </button>
  );
}
