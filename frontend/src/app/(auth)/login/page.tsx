"use client";
import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Mail, Lock, Phone } from "lucide-react";
import Link from "next/link";

type Tab = "email" | "phone";
type PhoneStep = "number" | "otp";

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
        <radialGradient id="ig" cx="30%" cy="107%" r="150%">
          <stop offset="0%" stopColor="#fdf497"/>
          <stop offset="5%" stopColor="#fdf497"/>
          <stop offset="45%" stopColor="#fd5949"/>
          <stop offset="60%" stopColor="#d6249f"/>
          <stop offset="90%" stopColor="#285AEB"/>
        </radialGradient>
      </defs>
      <rect width="24" height="24" rx="6" fill="url(#ig)"/>
      <circle cx="12" cy="12" r="4" stroke="white" strokeWidth="1.5" fill="none"/>
      <circle cx="17.5" cy="6.5" r="1" fill="white"/>
    </svg>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setAuth } = useAuthStore();

  const [tab, setTab] = useState<Tab>(
    (searchParams.get("tab") as Tab) === "phone" ? "phone" : "email"
  );
  const [phoneStep, setPhoneStep] = useState<PhoneStep>("number");

  // Email fields
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Phone fields
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleEmailLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const token = await authApi.login(email, password);
      const user = await authApi.me(token.access_token);
      setAuth(token.access_token, user);
      router.replace("/");
    } catch (err: any) {
      setError(err.message ?? "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleSendOtp(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await authApi.phoneRequestOtp(phone);
      setPhoneStep("otp");
    } catch (err: any) {
      setError(err.message ?? "Failed to send OTP");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOtp(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const token = await authApi.phoneVerify(phone, otp);
      const user = await authApi.me(token.access_token);
      setAuth(token.access_token, user);
      router.replace("/");
    } catch (err: any) {
      setError(err.message ?? "Invalid OTP");
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

  const switchTab = (t: Tab) => {
    setTab(t);
    setError("");
    setPhoneStep("number");
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 bg-bg">
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-black text-primary">turnup</h1>
        <p className="text-sm text-text-muted mt-1">Find your next great experience</p>
      </div>

      <div className="w-full max-w-sm space-y-5">
        <h2 className="text-2xl font-black text-text text-center">Welcome back</h2>

        {/* Tab switcher */}
        <div className="flex border-2 border-border bg-bg-elevated p-1 gap-1 rounded" role="tablist">
          {(["email", "phone"] as Tab[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => switchTab(t)}
              className={`flex-1 py-2 rounded text-sm font-bold uppercase tracking-wide transition-colors ${
                tab === t
                  ? "bg-primary text-white"
                  : "text-text-muted hover:text-text"
              }`}
            >
              {t === "email" ? "Email" : "Phone"}
            </button>
          ))}
        </div>

        {error && (
          <div className="px-4 py-3 rounded-2xl bg-error/10 border border-error/30 text-sm text-error">
            {error}
          </div>
        )}

        {/* Email tab */}
        {tab === "email" && (
          <form onSubmit={handleEmailLogin} className="space-y-3">
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              icon={<Mail size={16} />}
              required
            />
            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              icon={<Lock size={16} />}
              required
            />
            <Button type="submit" fullWidth size="lg" loading={loading} className="mt-2">
              Log In
            </Button>
          </form>
        )}

        {/* Phone tab */}
        {tab === "phone" && phoneStep === "number" && (
          <form onSubmit={handleSendOtp} className="space-y-3">
            <Input
              label="Phone Number"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1 555 000 0000"
              icon={<Phone size={16} />}
              required
            />
            <Button type="submit" fullWidth size="lg" loading={loading}>
              Send OTP
            </Button>
          </form>
        )}

        {tab === "phone" && phoneStep === "otp" && (
          <form onSubmit={handleVerifyOtp} className="space-y-3">
            <p className="text-sm text-text-muted text-center">
              Enter the 6-digit code sent to <span className="text-text font-medium">{phone}</span>
            </p>
            <Input
              label="OTP Code"
              type="text"
              inputMode="numeric"
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="000000"
              maxLength={6}
              required
            />
            <Button type="submit" fullWidth size="lg" loading={loading}>
              Verify & Log In
            </Button>
            <button
              type="button"
              onClick={() => { setPhoneStep("number"); setOtp(""); setError(""); }}
              className="w-full text-sm text-text-muted hover:text-text text-center"
            >
              Use a different number
            </button>
          </form>
        )}

        {/* OAuth divider */}
        <div className="flex items-center gap-3">
          <div className="flex-1 h-0.5 bg-border" />
          <span className="text-xs font-bold text-text-muted uppercase tracking-wide">or</span>
          <div className="flex-1 h-0.5 bg-border" />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => handleOAuth("google")}
            className="flex items-center justify-center gap-2 px-4 py-3 rounded border-2 border-border bg-bg-card text-sm font-bold text-text hover:bg-bg-elevated shadow-brutal-sm hover:shadow-brutal transition-all duration-100 active:shadow-none active:translate-x-0.5 active:translate-y-0.5"
          >
            <GoogleIcon />
            Google
          </button>
          <button
            type="button"
            onClick={() => handleOAuth("instagram")}
            className="flex items-center justify-center gap-2 px-4 py-3 rounded border-2 border-border bg-bg-card text-sm font-bold text-text hover:bg-bg-elevated shadow-brutal-sm hover:shadow-brutal transition-all duration-100 active:shadow-none active:translate-x-0.5 active:translate-y-0.5"
          >
            <InstagramIcon />
            Instagram
          </button>
        </div>

        <p className="text-center text-sm text-text-muted">
          Don't have an account?{" "}
          <Link href="/signup" className="text-primary font-medium hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
