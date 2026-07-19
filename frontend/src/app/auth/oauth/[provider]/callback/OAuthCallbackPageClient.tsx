"use client";
import { useEffect, useState } from "react";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Mail } from "lucide-react";

export default function OAuthCallbackPage() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const { setAuth } = useAuthStore();

  const provider = params.provider as string;
  const code = searchParams.get("code");
  const state = searchParams.get("state") ?? "";

  const [step, setStep] = useState<"loading" | "email" | "error">("loading");
  const [partialToken, setPartialToken] = useState("");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!code) {
      setError("No authorization code received from provider.");
      setStep("error");
      return;
    }

    authApi
      .oauthCallback(provider, code, state)
      .then(async (data) => {
        if (data.requires_email) {
          setPartialToken(data.partial_token!);
          setStep("email");
        } else if (data.access_token) {
          const user = await authApi.me(data.access_token);
          setAuth(data.access_token, user);
          router.replace("/");
        } else {
          throw new Error("Unexpected response from server");
        }
      })
      .catch((err) => {
        setError(err.message ?? "Authentication failed");
        setStep("error");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleEmailSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const token = await authApi.oauthComplete(partialToken, email);
      const user = await authApi.me(token.access_token);
      setAuth(token.access_token, user);
      router.replace("/onboarding");
    } catch (err: any) {
      setError(err.message ?? "Failed to complete sign-up");
    } finally {
      setSubmitting(false);
    }
  }

  if (step === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-text-muted">Completing sign-in…</p>
        </div>
      </div>
    );
  }

  if (step === "error") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6 bg-bg gap-4">
        <h2 className="text-xl font-bold text-text">Sign-in failed</h2>
        <p className="text-sm text-error text-center">{error}</p>
        <button
          onClick={() => router.replace("/login")}
          className="text-sm text-primary font-medium hover:underline"
        >
          Back to login
        </button>
      </div>
    );
  }

  // step === "email" — Instagram flow: collect email
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 bg-bg">
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-black text-primary">turnup</h1>
      </div>
      <div className="w-full max-w-sm space-y-4">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-text">One more step</h2>
          <p className="text-sm text-text-muted mt-1">
            Instagram doesn't share your email. Enter it to finish creating your account.
          </p>
        </div>

        {error && (
          <div className="px-4 py-3 rounded-2xl bg-error/10 border border-error/30 text-sm text-error">
            {error}
          </div>
        )}

        <form onSubmit={handleEmailSubmit} className="space-y-3">
          <Input
            label="Email address"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            icon={<Mail size={16} />}
            required
          />
          <Button type="submit" fullWidth size="lg" loading={submitting}>
            Continue
          </Button>
        </form>
      </div>
    </div>
  );
}
