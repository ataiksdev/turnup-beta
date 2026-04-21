"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { Music, Moon, Palette, Utensils, Monitor, Trophy, Laugh, Leaf, Check, type LucideIcon } from "lucide-react";

const CATEGORIES: { slug: string; label: string; icon: LucideIcon; color: string }[] = [
  { slug: "music",     label: "Music",       icon: Music,    color: "#A855F7" },
  { slug: "nightlife", label: "Nightlife",    icon: Moon,     color: "#3B82F6" },
  { slug: "arts",      label: "Arts",         icon: Palette,  color: "#A855F7" },
  { slug: "food",      label: "Food & Drink", icon: Utensils, color: "#EF4444" },
  { slug: "tech",      label: "Tech",         icon: Monitor,  color: "#06B6D4" },
  { slug: "sports",    label: "Sports",       icon: Trophy,   color: "#22C55E" },
  { slug: "comedy",    label: "Comedy",       icon: Laugh,    color: "#EAB308" },
  { slug: "wellness",  label: "Wellness",     icon: Leaf,     color: "#10B981" },
];

const MIN_SELECTIONS = 1;

export default function OnboardingPage() {
  const router = useRouter();
  const { token, setUser } = useAuthStore();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function toggle(slug: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }

  async function handleSubmit() {
    if (!token || selected.size < MIN_SELECTIONS) return;
    setLoading(true);
    setError("");
    try {
      await authApi.completeOnboarding(token, Array.from(selected));
      const updated = await authApi.me(token);
      setUser(updated);
      router.replace("/");
    } catch (err: any) {
      setError(err.message ?? "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-bg px-6 py-10 safe-top">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-2 mb-8"
      >
        <h1 className="text-3xl font-black text-text">
          What gets you <span className="text-primary">hyped?</span>
        </h1>
        <p className="text-sm text-text-secondary">
          Select the types of events you love. We'll personalise your feed.
        </p>
        <p className="text-xs text-text-muted">
          Pick at least {MIN_SELECTIONS} · {selected.size} selected
        </p>
      </motion.div>

      {/* Category grid */}
      <div className="grid grid-cols-2 gap-3 flex-1">
        {CATEGORIES.map((cat, i) => {
          const isSelected = selected.has(cat.slug);
          const CatIcon = cat.icon;
          return (
            <motion.button
              key={cat.slug}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              onClick={() => toggle(cat.slug)}
              className={cn(
                "relative flex flex-col items-center justify-center gap-2",
                "h-28 rounded-3xl border-2 transition-all duration-200 active:scale-95",
                isSelected
                  ? "border-transparent shadow-glow"
                  : "bg-bg-card border-border hover:border-border-strong",
              )}
              style={isSelected ? {
                background: `linear-gradient(135deg, ${cat.color}22, ${cat.color}44)`,
                borderColor: cat.color,
              } : undefined}
            >
              <CatIcon size={28} style={{ color: isSelected ? cat.color : undefined }} className={isSelected ? "" : "text-text-muted"} aria-hidden />
              <span className={cn(
                "text-sm font-semibold",
                isSelected ? "text-white" : "text-text-secondary",
              )}>
                {cat.label}
              </span>
              {isSelected && (
                <motion.span
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="absolute top-2.5 right-2.5 w-5 h-5 rounded-full bg-white/90 flex items-center justify-center"
                >
                  <Check size={11} style={{ color: cat.color }} aria-hidden />
                </motion.span>
              )}
            </motion.button>
          );
        })}
      </div>

      {/* Error */}
      {error && (
        <p className="text-sm text-error text-center mt-3">{error}</p>
      )}

      {/* Actions */}
      <div className="mt-6 space-y-3">
        <Button
          fullWidth
          size="lg"
          loading={loading}
          disabled={selected.size < MIN_SELECTIONS}
          onClick={handleSubmit}
        >
          Continue → Let's go!
        </Button>
        <button
          onClick={() => router.replace("/")}
          className="w-full text-sm text-text-muted text-center py-2 hover:text-text-secondary"
        >
          Skip for now
        </button>
      </div>
    </div>
  );
}
