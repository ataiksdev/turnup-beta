"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/Button";
import { AuthShell, Notice } from "@/components/layout/AuthShell";

function VerifyEmail() {
  const token = useSearchParams().get("token") ?? "";
  const { token: authToken, setUser } = useAuthStore();
  const [state, setState] = useState<"working" | "ok" | "error">(token ? "working" : "error");
  const [error, setError] = useState(token ? "" : "This verification link is incomplete.");
  const started = useRef(false); // the token is single-use: never send it twice

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    authApi.verifyEmail(token)
      .then(async () => {
        setState("ok");
        if (authToken) {
          try { setUser(await authApi.me(authToken)); } catch { /* not critical */ }
        }
      })
      .catch((err) => {
        setState("error");
        setError(err.message ?? "Could not verify your email.");
      });
  }, [token, authToken, setUser]);

  return (
    <AuthShell title="Verify your email">
      {state === "working" && <Notice tone="info">Verifying…</Notice>}
      {state === "ok" && (
        <>
          <Notice tone="success">Your email is verified. Thanks!</Notice>
          <Link href={authToken ? "/" : "/login"}>
            <Button fullWidth size="lg">{authToken ? "Continue" : "Log in"}</Button>
          </Link>
        </>
      )}
      {state === "error" && (
        <>
          <Notice tone="error">{error}</Notice>
          <p className="text-center text-sm text-text-muted">
            Links expire after 24 hours. You can send a new one from{" "}
            <Link href={authToken ? "/settings" : "/login?next=/settings"} className="text-primary font-medium hover:underline">
              your account settings
            </Link>.
          </p>
        </>
      )}
    </AuthShell>
  );
}

export default function VerifyEmailPage() {
  return <Suspense><VerifyEmail /></Suspense>;
}
