"use client";
import { useState } from "react";
import Link from "next/link";
import { Mail } from "lucide-react";
import { authApi } from "@/lib/api";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { AuthShell, Notice } from "@/components/layout/AuthShell";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await authApi.forgotPassword(email.trim());
      setSent(true);
    } catch (err: any) {
      setError(err.message ?? "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Reset your password">
      {sent ? (
        <>
          <Notice tone="success">
            If <strong>{email}</strong>{" "}has a Turnup account, we&apos;ve sent a link to reset your
            password. It expires in 60 minutes.
          </Notice>
          <p className="text-center text-sm text-text-muted">
            Didn&apos;t get it? Check your spam folder or{" "}
            <button onClick={() => setSent(false)} className="text-primary font-medium hover:underline">
              try again
            </button>.
          </p>
        </>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          <p className="text-sm text-text-muted text-center">
            Enter the email on your account and we&apos;ll send you a reset link.
          </p>
          {error && <Notice tone="error">{error}</Notice>}
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@example.com"
            icon={<Mail size={16} />}
            required
          />
          <Button type="submit" fullWidth size="lg" loading={loading}>Send reset link</Button>
        </form>
      )}
      <p className="text-center text-sm text-text-muted">
        <Link href="/login" className="text-primary font-medium hover:underline">Back to log in</Link>
      </p>
    </AuthShell>
  );
}
