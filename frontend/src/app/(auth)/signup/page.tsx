"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Mail, Lock, User, AtSign } from "lucide-react";
import Link from "next/link";

export default function SignupPage() {
  const router = useRouter();
  const { setAuth } = useAuthStore();

  const [form, setForm] = useState({
    full_name: "", username: "", email: "", password: "",
  });
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
      // Redirect to onboarding for category preferences
      router.replace("/onboarding");
    } catch (err: any) {
      setError(err.message ?? "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 bg-bg">
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-black text-primary">turnup</h1>
        <p className="text-sm text-text-muted mt-1">Find your next great experience</p>
      </div>

      <div className="w-full max-w-sm space-y-4">
        <h2 className="text-2xl font-bold text-text text-center">Create your account</h2>

        {error && (
          <div className="px-4 py-3 rounded-2xl bg-error/10 border border-error/30 text-sm text-error">
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
            Create Account
          </Button>
        </form>

        <p className="text-center text-sm text-text-muted">
          Already have an account?{" "}
          <Link href="/login" className="text-primary font-medium hover:underline">Log in</Link>
        </p>
      </div>
    </div>
  );
}
