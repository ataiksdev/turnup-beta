"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { authApi } from "@/lib/api";
import { useFinishLogin } from "@/lib/session";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { AuthShell, Notice } from "@/components/layout/AuthShell";

// Landing page for the emailed magic login link (/auth/magic?token=...).
function MagicLink() {
  const token = useSearchParams().get("token") ?? "";
  const finishLogin = useFinishLogin();
  const [error, setError] = useState(token ? "" : "This login link is incomplete.");
  const [tempToken, setTempToken] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const started = useRef(false); // single-use token: never send it twice

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    authApi.verifyMagicLink(token)
      .then((result) => {
        if ("requires_2fa" in result) setTempToken(result.temp_token);
        else return finishLogin(result.access_token);
      })
      .catch((err) => setError(err.message ?? "This login link didn't work."));
  }, [token, finishLogin]);

  async function submit2fa(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const t = await authApi.verify2fa(tempToken, code.trim());
      await finishLogin(t.access_token);
    } catch (err: any) {
      setError(err.message ?? "Invalid code");
    } finally {
      setLoading(false);
    }
  }

  if (tempToken) {
    return (
      <AuthShell title="Two-factor authentication">
        <form onSubmit={submit2fa} className="space-y-3">
          <p className="text-sm text-text-muted text-center">
            Enter the code from your authenticator app, or a backup code.
          </p>
          {error && <Notice tone="error">{error}</Notice>}
          <Input
            label="Authentication code"
            autoComplete="one-time-code"
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value.slice(0, 9))}
            placeholder="123456 or ABCD-EF12"
            icon={<ShieldCheck size={16} />}
            required
          />
          <Button type="submit" fullWidth size="lg" loading={loading}>Verify & Log In</Button>
        </form>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Signing you in">
      {error ? (
        <>
          <Notice tone="error">{error}</Notice>
          <p className="text-center text-sm text-text-muted">
            Login links work once and expire after 15 minutes.{" "}
            <Link href="/login" className="text-primary font-medium hover:underline">Get a new one</Link>.
          </p>
        </>
      ) : (
        <Notice tone="info">One moment…</Notice>
      )}
    </AuthShell>
  );
}

export default function MagicLinkPage() {
  return <Suspense><MagicLink /></Suspense>;
}
