"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Mail, Lock, User, AtSign, ChevronLeft } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

type Role = "attendee" | "organizer";
type Step = "role" | "form";

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.964 10.706A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.706V4.962H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.038l3.007-2.332z"/>
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.962L3.964 7.294C4.672 5.163 6.656 3.58 9 3.58z"/>
    </svg>
  );
}

function InstagramIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <defs>
        <radialGradient id="ig2" cx="30%" cy="107%" r="150%">
          <stop offset="0%" stopColor="#fdf497"/>
          <stop offset="5%" stopColor="#fdf497"/>
          <stop offset="45%" stopColor="#fd5949"/>
          <stop offset="60%" stopColor="#d6249f"/>
          <stop offset="90%" stopColor="#285AEB"/>
        </radialGradient>
      </defs>
      <rect width="24" height="24" rx="6" fill="url(#ig2)"/>
      <circle cx="12" cy="12" r="4" stroke="white" strokeWidth="1.5" fill="none"/>
      <circle cx="17.5" cy="6.5" r="1" fill="white"/>
    </svg>
  );
}

const ROLE_OPTIONS: { role: Role; emoji: string; title: string; description: string }[] = [
  {
    role: "attendee",
    emoji: "🎟️",
    title: "Discover Events",
    description: "Find concerts, parties, festivals, and experiences near you",
  },
  {
    role: "organizer",
    emoji: "🎤",
    title: "Host Events",
    description: "Create and manage events, sell tickets, grow your audience",
  },
];

export default function SignupPage() {
  const router = useRouter();
  const { setAuth } = useAuthStore();

  const [step, setStep] = useState<Step>("role");
  const [role, setRole] = useState<Role | null>(null);

  const [form, setForm] = useState({ full_name: "", username: "", email: "", password: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }));

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const token = await authApi.register(form);
      const user = await authApi.me(token.access_token);
      setAuth(token.access_token, user);
      router.replace(role === "organizer" ? "/onboarding/organizer" : "/onboarding");
    } catch (err: any) {
      setError(err.message ?? "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleOAuth(provider: "google" | "instagram") {
    try {
      const { url } = await authApi.getOAuthUrl(provider);
      window.location.href = url;
    } catch (err: any) {
      setError(err.message ?? "OAuth unavailable");
    }
  }

  // ── Step 1: Role selection ─────────────────────────────────────────────────
  if (step === "role") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6 bg-bg">
        <div className="mb-8 text-center">
          <h1 className="text-4xl font-black text-primary">turnup</h1>
          <p className="text-sm text-text-muted mt-1">Find your next great experience</p>
        </div>

        <div className="w-full max-w-sm space-y-5">
          <div className="space-y-1 text-center">
            <h2 className="text-2xl font-black text-text">What brings you here?</h2>
            <p className="text-xs font-bold text-text-muted uppercase tracking-widest">
              Choose your path
            </p>
          </div>

          <div className="space-y-3">
            {ROLE_OPTIONS.map(({ role: r, emoji, title, description }) => (
              <button
                key={r}
                onClick={() => setRole(r)}
                className={cn(
                  "w-full text-left p-5 rounded border-2 transition-all duration-100",
                  "shadow-brutal hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-lg",
                  "active:translate-x-0.5 active:translate-y-0.5 active:shadow-none",
                  role === r
                    ? "border-primary bg-primary/10"
                    : "border-border bg-bg-card hover:border-primary/60",
                )}
              >
                <div className="flex items-start gap-4">
                  <span className="text-4xl leading-none mt-0.5">{emoji}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="font-black text-text text-base uppercase tracking-wide">{title}</span>
                      {role === r && (
                        <span className="w-5 h-5 rounded-full bg-primary flex items-center justify-center shrink-0">
                          <span className="text-white text-[11px] font-black">✓</span>
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-text-muted mt-1 leading-relaxed">{description}</p>
                  </div>
                </div>
              </button>
            ))}
          </div>

          <Button fullWidth size="lg" disabled={!role} onClick={() => setStep("form")}>
            Continue
          </Button>

          <p className="text-center text-sm text-text-muted">
            Already have an account?{" "}
            <Link href="/login" className="text-primary font-medium hover:underline">Log in</Link>
          </p>
        </div>
      </div>
    );
  }

  // ── Step 2: Registration form ──────────────────────────────────────────────
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 bg-bg">
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-black text-primary">turnup</h1>
        <p className="text-sm text-text-muted mt-1">
          {role === "organizer" ? "Set up your organizer account" : "Find your next great experience"}
        </p>
      </div>

      <div className="w-full max-w-sm space-y-4">
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setStep("role"); setError(""); }}
            className="p-1.5 -ml-1.5 rounded hover:bg-bg-elevated transition-colors"
            aria-label="Back to role selection"
          >
            <ChevronLeft size={18} className="text-text-muted" />
          </button>
          <h2 className="text-2xl font-black text-text">
            {role === "organizer" ? "Organizer account" : "Create your account"}
          </h2>
        </div>

        <div className={cn(
          "inline-flex items-center gap-2 px-3 py-1.5 rounded border-2 text-xs font-black uppercase tracking-widest",
          role === "organizer"
            ? "border-primary text-primary bg-primary/10"
            : "border-border text-text-muted bg-bg-elevated",
        )}>
          {role === "organizer" ? "🎤 Organizer" : "🎟️ Event goer"}
        </div>

        {error && (
          <div className="px-4 py-3 rounded bg-error/10 border border-error/30 text-sm text-error">
            {error}
          </div>
        )}

        <form onSubmit={handleSignup} className="space-y-3">
          <Input label="Full Name" type="text" value={form.full_name} onChange={set("full_name")}
            placeholder="Your name" icon={<User size={16} />} required />
          <Input label="Username" type="text" value={form.username} onChange={set("username")}
            placeholder="coolperson" icon={<AtSign size={16} />}
            pattern="^[a-zA-Z0-9_]+$" minLength={3} maxLength={30} required />
          <Input label="Email" type="email" value={form.email} onChange={set("email")}
            placeholder="you@example.com" icon={<Mail size={16} />} required />
          <Input label="Password" type="password" value={form.password} onChange={set("password")}
            placeholder="Min. 6 characters" icon={<Lock size={16} />} minLength={6} required />
          <Button type="submit" fullWidth size="lg" loading={loading} className="mt-2">
            {role === "organizer" ? "Create Organizer Account" : "Create Account"}
          </Button>
        </form>

        <div className="flex items-center gap-3">
          <div className="flex-1 h-0.5 bg-border" />
          <span className="text-xs font-bold text-text-muted uppercase tracking-wide">or</span>
          <div className="flex-1 h-0.5 bg-border" />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <button type="button" onClick={() => handleOAuth("google")}
            className="flex items-center justify-center gap-2 px-4 py-3 rounded border-2 border-border bg-bg-card text-sm font-bold text-text hover:bg-bg-elevated shadow-brutal-sm hover:shadow-brutal transition-all duration-100 active:shadow-none active:translate-x-0.5 active:translate-y-0.5">
            <GoogleIcon /> Google
          </button>
          <button type="button" onClick={() => handleOAuth("instagram")}
            className="flex items-center justify-center gap-2 px-4 py-3 rounded border-2 border-border bg-bg-card text-sm font-bold text-text hover:bg-bg-elevated shadow-brutal-sm hover:shadow-brutal transition-all duration-100 active:shadow-none active:translate-x-0.5 active:translate-y-0.5">
            <InstagramIcon /> Instagram
          </button>
        </div>

        <p className="text-center text-sm text-text-muted">
          Already have an account?{" "}
          <Link href="/login" className="text-primary font-medium hover:underline">Log in</Link>
        </p>
        <p className="text-center text-sm text-text-muted">
          Prefer phone?{" "}
          <Link href="/login?tab=phone" className="text-primary font-medium hover:underline">
            Sign up with phone number
          </Link>
        </p>
      </div>
    </div>
  );
}
