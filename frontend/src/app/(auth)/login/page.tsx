"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Mail, Lock } from "lucide-react";
import Link from "next/link";

export default function LoginPage() {
  const router = useRouter();
  const { setAuth } = useAuthStore();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleLogin(e: React.FormEvent) {
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

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 bg-bg">
      {/* Logo */}
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-black text-primary">turnup</h1>
        <p className="text-sm text-text-muted mt-1">Find your next great experience</p>
      </div>

      <div className="w-full max-w-sm space-y-4">
        <h2 className="text-2xl font-bold text-text text-center">Welcome back</h2>

        {error && (
          <div className="px-4 py-3 rounded-2xl bg-error/10 border border-error/30 text-sm text-error">
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-3">
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
