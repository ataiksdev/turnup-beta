"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";
import {
  Music, Moon, Palette, Utensils, Monitor, Trophy, Laugh, Leaf, Check,
  Clock, Star, Calendar, Ticket, Coins, CreditCard, Crown,
  type LucideIcon,
} from "lucide-react";

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

const CITIES = ["Lagos", "Abuja", "Port Harcourt", "Ibadan", "Kano", "Enugu"];

export default function OnboardingPage() {
  const router = useRouter();
  const { token, setUser } = useAuthStore();

  const [step, setStep] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [city, setCity] = useState("");
  const [goesOut, setGoesOut] = useState("");
  const [budget, setBudget] = useState("");
  const [format, setFormat] = useState("");
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
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const updated = await authApi.completeOnboarding(token, {
        category_preferences: Array.from(selected),
        city: city || undefined,
        goes_out_when: goesOut || undefined,
        price_sensitivity: budget || undefined,
        event_format_pref: format || undefined,
      });
      setUser(updated);
      router.replace("/");
    } catch (err: any) {
      setError(err.message ?? "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const customCityValue = CITIES.includes(city) ? "" : city;

  return (
    <div className="min-h-screen flex flex-col bg-bg px-6 py-10 safe-top">
      <div className="mb-2">
        <p className="text-xs font-bold text-text-muted uppercase tracking-widest mb-2">Step {step} of 3</p>
        <div className="h-1 bg-bg-elevated rounded-full mb-6">
          <div
            className="h-1 bg-primary rounded-full transition-all duration-300"
            style={{ width: `${(step / 3) * 100}%` }}
          />
        </div>
      </div>

      {step === 1 && (
        <motion.div
          key="step1"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col flex-1"
        >
          <div className="space-y-2 mb-8">
            <h1 className="text-3xl font-black text-text">
              What gets you <span className="text-primary">hyped?</span>
            </h1>
            <p className="text-sm text-text-secondary">
              Select the types of events you love. We'll personalise your feed.
            </p>
            <p className="text-xs text-text-muted">
              Pick at least 1 · {selected.size} selected
            </p>
          </div>

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
                  <CatIcon
                    size={28}
                    style={{ color: isSelected ? cat.color : undefined }}
                    className={isSelected ? "" : "text-text-muted"}
                    aria-hidden
                  />
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

          <div className="mt-6 space-y-3">
            <Button fullWidth size="lg" disabled={selected.size < 1} onClick={() => setStep(2)}>
              Continue →
            </Button>
            <button
              onClick={() => router.replace("/")}
              className="w-full text-sm text-text-muted text-center py-2 hover:text-text-secondary"
            >
              Skip for now
            </button>
          </div>
        </motion.div>
      )}

      {step === 2 && (
        <motion.div
          key="step2"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col flex-1"
        >
          <div className="space-y-2 mb-8">
            <h1 className="text-3xl font-black text-text">
              Where & <span className="text-primary">When</span>
            </h1>
            <p className="text-sm text-text-secondary">We'll show you what's happening near you.</p>
          </div>

          <div className="space-y-6 flex-1">
            <div className="space-y-3">
              <p className="text-xs font-black text-text-muted uppercase tracking-widest">Your city</p>
              <div className="flex flex-wrap gap-2">
                {CITIES.map((c) => (
                  <button
                    key={c}
                    onClick={() => setCity(city === c ? "" : c)}
                    className={cn(
                      "px-4 py-2 rounded-full border-2 text-sm font-bold transition-all",
                      city === c
                        ? "bg-primary text-white border-primary"
                        : "bg-bg-surface border-border text-text-secondary hover:border-primary",
                    )}
                  >
                    {c}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={customCityValue}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Another city..."
                className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary transition-all"
              />
            </div>

            <div className="space-y-3">
              <p className="text-xs font-black text-text-muted uppercase tracking-widest">When do you go out?</p>
              <div className="space-y-2">
                {[
                  { label: "Weekdays", sub: "Mon–Fri", icon: Clock, value: "weekdays" },
                  { label: "Weekends", sub: "Fri–Sun", icon: Star, value: "weekends" },
                  { label: "Anytime",  sub: "Any day works", icon: Calendar, value: "any" },
                ].map(({ label, sub, icon: Icon, value }) => (
                  <button
                    key={value}
                    onClick={() => setGoesOut(goesOut === value ? "" : value)}
                    className={cn(
                      "w-full border-2 border-border rounded-xl p-4 flex items-center gap-3 transition-all",
                      goesOut === value
                        ? "border-primary bg-primary/10"
                        : "bg-bg-card hover:border-border-strong",
                    )}
                  >
                    <Icon
                      size={20}
                      className={goesOut === value ? "text-primary" : "text-text-muted"}
                      aria-hidden
                    />
                    <div className="text-left">
                      <p className={cn("text-sm font-bold", goesOut === value ? "text-primary" : "text-text")}>
                        {label}
                      </p>
                      <p className="text-xs text-text-muted">{sub}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-6 space-y-3">
            <Button fullWidth size="lg" onClick={() => setStep(3)}>
              Continue →
            </Button>
            <div className="flex justify-between">
              <button
                onClick={() => setStep(1)}
                className="text-sm text-text-muted py-2 hover:text-text-secondary"
              >
                ← Back
              </button>
              <button
                onClick={() => router.replace("/")}
                className="text-sm text-text-muted py-2 hover:text-text-secondary"
              >
                Skip for now
              </button>
            </div>
          </div>
        </motion.div>
      )}

      {step === 3 && (
        <motion.div
          key="step3"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col flex-1"
        >
          <div className="space-y-2 mb-8">
            <h1 className="text-3xl font-black text-text">
              Budget & <span className="text-primary">Format</span>
            </h1>
            <p className="text-sm text-text-secondary">
              So we don't suggest sold-out VIP tables when you just want a free event.
            </p>
          </div>

          <div className="space-y-6 flex-1">
            <div className="space-y-3">
              <p className="text-xs font-black text-text-muted uppercase tracking-widest">Budget</p>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: "Free only",  sub: "₦0 events",       icon: Ticket,     value: "free"   },
                  { label: "Budget",     sub: "₦0–₦5k",          icon: Coins,      value: "budget" },
                  { label: "Mid-range",  sub: "₦5k–₦20k",        icon: CreditCard, value: "mid"    },
                  { label: "No limit",   sub: "Sky's the limit",  icon: Crown,      value: "any"    },
                ].map(({ label, sub, icon: Icon, value }) => (
                  <button
                    key={value}
                    onClick={() => setBudget(budget === value ? "" : value)}
                    className={cn(
                      "border-2 rounded-xl p-4 flex flex-col gap-2 transition-all text-left",
                      budget === value
                        ? "border-primary bg-primary/10"
                        : "bg-bg-card border-border hover:border-border-strong",
                    )}
                  >
                    <Icon
                      size={20}
                      className={budget === value ? "text-primary" : "text-text-muted"}
                      aria-hidden
                    />
                    <div>
                      <p className={cn("text-sm font-bold", budget === value ? "text-primary" : "text-text")}>
                        {label}
                      </p>
                      <p className="text-xs text-text-muted">{sub}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-3">
              <p className="text-xs font-black text-text-muted uppercase tracking-widest">Format</p>
              <div className="flex gap-2">
                {[
                  { label: "🏟 In-person", value: "physical" },
                  { label: "💻 Online",    value: "virtual"  },
                  { label: "🌐 Both",      value: "both"     },
                ].map(({ label, value }) => (
                  <button
                    key={value}
                    onClick={() => setFormat(format === value ? "" : value)}
                    className={cn(
                      "flex-1 py-2.5 rounded-full border-2 text-sm font-bold transition-all",
                      format === value
                        ? "bg-primary text-white border-primary"
                        : "bg-bg-surface border-border text-text-secondary hover:border-primary",
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {error && <p className="text-sm text-error text-center mt-3">{error}</p>}

          <div className="mt-6 space-y-3">
            <Button fullWidth size="lg" loading={loading} onClick={handleSubmit}>
              Let's go!
            </Button>
            <div className="flex justify-between">
              <button
                onClick={() => setStep(2)}
                className="text-sm text-text-muted py-2 hover:text-text-secondary"
              >
                ← Back
              </button>
              <button
                onClick={() => router.replace("/")}
                className="text-sm text-text-muted py-2 hover:text-text-secondary"
              >
                Skip for now
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}
