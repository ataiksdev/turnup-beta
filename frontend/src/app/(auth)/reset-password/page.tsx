"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Lock } from "lucide-react";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { AuthShell, Notice } from "@/components/layout/AuthShell";

const MIN_LENGTH = 8;

function ResetPassword() {
  const token = useSearchParams().get("token") ?? "";
  const { logout } = useAuthStore();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < MIN_LENGTH) return setError(`Use at least ${MIN_LENGTH} characters.`);
    if (password !== confirm) return setError("The two passwords don't match.");
    setLoading(true);
    try {
      await authApi.resetPassword(token, password);
      logout(); // the server just signed out every session, including this browser's
      setDone(true);
    } catch (err: any) {
      setError(err.message ?? "Could not reset your password.");
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <AuthShell title="Reset your password">
        <Notice tone="error">This reset link is incomplete. Request a new one.</Notice>
        <p className="text-center text-sm">
          <Link href="/forgot-password" className="text-primary font-medium hover:underline">Request a new link</Link>
        </p>
      </AuthShell>
    );
  }

  if (done) {
    return (
      <AuthShell title="Password updated">
        <Notice tone="success">
          Your password has been changed and you&apos;ve been signed out everywhere. Log in with your new password.
        </Notice>
        <Link href="/login"><Button fullWidth size="lg">Log in</Button></Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Choose a new password">
      <form onSubmit={handleSubmit} className="space-y-3">
        {error && (
          <Notice tone="error">
            {error}
            {/expired|invalid/i.test(error) && (
              <> <Link href="/forgot-password" className="underline font-bold">Request a new link</Link>.</>
            )}
          </Notice>
        )}
        <Input
          label="New password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={`At least ${MIN_LENGTH} characters`}
          icon={<Lock size={16} />}
          required
        />
        <Input
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          icon={<Lock size={16} />}
          required
        />
        <Button type="submit" fullWidth size="lg" loading={loading}>Update password</Button>
      </form>
    </AuthShell>
  );
}

export default function ResetPasswordPage() {
  return <Suspense><ResetPassword /></Suspense>;
}
