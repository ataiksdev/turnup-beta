"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { authApi } from "@/lib/api";
import { bookingsApi } from "@/lib/marketplace";
import { useAuthStore } from "@/store/auth";

/** Paystack sends the payer back here (?reference=...&next=...). Confirms the payment with the
 *  API (the webhook does the same independently) and continues to `next`. */
function Callback() {
  const search = useSearchParams();
  const router = useRouter();
  const { token, hasHydrated, setUser } = useAuthStore();
  const [message, setMessage] = useState("Confirming your payment…");
  const reference = search.get("reference") ?? search.get("trxref") ?? "";
  const rawNext = search.get("next") ?? "/";
  const next = rawNext.startsWith("/") && !rawNext.startsWith("//") ? rawNext : "/";

  useEffect(() => {
    if (!hasHydrated) return;
    if (!token || !reference) {
      router.replace(next);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const r = await bookingsApi.verify(token, reference);
        if (reference.startsWith("sub_")) setUser(await authApi.me(token));
        if (cancelled) return;
        if (r.status === "ok" || r.status === "already") router.replace(next);
        else setMessage(r.status === "abandoned" || r.status === "failed"
          ? "The payment didn't go through. You can try again."
          : "We're still waiting for the payment to clear. It will show up shortly.");
      } catch (err: any) {
        if (!cancelled) setMessage(err?.message ?? "We couldn't confirm the payment yet. It will show up shortly.");
      }
    })();
    return () => { cancelled = true; };
  }, [hasHydrated, token, reference]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="min-h-screen bg-bg flex flex-col items-center justify-center gap-4 px-6 text-center">
      <Loader2 className="animate-spin text-primary" size={28} aria-hidden />
      <p className="text-sm font-bold text-text">{message}</p>
      <button onClick={() => router.replace(next)} className="text-xs font-bold text-primary underline">Continue</button>
    </main>
  );
}

export default function Page() {
  return <Suspense><Callback /></Suspense>;
}
