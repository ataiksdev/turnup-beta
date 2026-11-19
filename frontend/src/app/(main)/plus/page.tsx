"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { CalendarHeart, Check, Gift, Sparkles, Ticket } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage, authApi } from "@/lib/api";
import { goToPayment, naira, paymentCallback, plusApi } from "@/lib/marketplace";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";

export default function PlusPage() {
  const { token, hasHydrated, setUser } = useAuthStore();
  const qc = useQueryClient();
  const [plan, setPlan] = useState("turnup_plus_monthly");
  const [error, setError] = useState("");
  const [terms, setTerms] = useState(false);
  const plans = useQuery({ queryKey: ["plus", "plans"], queryFn: plusApi.plans });
  const me = useQuery({ queryKey: ["plus", "me"], queryFn: () => plusApi.me(token!), enabled: hasHydrated && !!token });

  const subscribe = useMutation({
    mutationFn: () => plusApi.subscribe(token!, plan, paymentCallback("/plus")),
    onSuccess: goToPayment, onError: (e) => setError(apiErrorMessage(e, "Couldn't start the payment.")),
  });
  const cancel = useMutation({
    mutationFn: () => plusApi.cancel(token!),
    onSuccess: async () => { qc.invalidateQueries({ queryKey: ["plus"] }); setUser(await authApi.me(token!)); },
    onError: (e) => setError(apiErrorMessage(e, "Couldn't cancel.")),
  });
  const settings = useMutation({
    mutationFn: (body: { show_plus_badge?: boolean; wrapped_opt_in?: boolean }) => plusApi.settings(token!, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plus", "me"] }),
  });

  const m = me.data;
  return (
    <div className="pb-24">
      <TopBar back title="Turnup+" />
      <div className="px-4 py-4 space-y-5">
        <header className="p-5 rounded border-2 border-border bg-primary text-on-primary shadow-brutal space-y-1">
          <Sparkles size={22} aria-hidden />
          <h1 className="text-2xl font-black">Turnup+</h1>
          <p className="text-sm opacity-90">Get in first, skip the queue, and get deals from venues and organizers.</p>
        </header>

        {m?.is_plus ? (
          <section className="p-4 rounded border-2 border-border bg-bg-card space-y-3">
            <p className="text-sm font-black text-text">You're a member</p>
            <p className="text-xs text-text-secondary">
              {m.renews ? "Renews" : "Ends"} {m.until ? format(new Date(m.until), "d MMM yyyy") : ""}
              {m.status === "past_due" && " · your last payment failed; update your card to keep your perks"}
            </p>
            <div className="grid grid-cols-3 gap-2 text-center">
              <Link href="/plus/deals" className="p-2 rounded border-2 border-border text-xs font-bold text-text"><Gift size={16} className="mx-auto text-primary" aria-hidden />Deals</Link>
              <Link href="/plus/weekend" className="p-2 rounded border-2 border-border text-xs font-bold text-text"><CalendarHeart size={16} className="mx-auto text-primary" aria-hidden />Weekend picks</Link>
              <Link href="/plus/wrapped" className="p-2 rounded border-2 border-border text-xs font-bold text-text"><Ticket size={16} className="mx-auto text-primary" aria-hidden />Wrapped</Link>
            </div>
            <label className="flex items-center justify-between text-sm text-text">
              Show the Plus badge on my profile
              <input type="checkbox" checked={m.show_plus_badge} onChange={(e) => settings.mutate({ show_plus_badge: e.target.checked })} />
            </label>
            <label className="flex items-center justify-between text-sm text-text">
              Let friends see me in their Wrapped
              <input type="checkbox" checked={m.wrapped_opt_in} onChange={(e) => settings.mutate({ wrapped_opt_in: e.target.checked })} />
            </label>
            {m.renews && (
              <Button variant="ghost" size="sm" loading={cancel.isPending} onClick={() => cancel.mutate()}>
                Cancel renewal (perks last until the end of the period)
              </Button>
            )}
          </section>
        ) : (
          <section className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              {plans.data?.plans.map((p) => (
                <button key={p.code} onClick={() => setPlan(p.code)} aria-pressed={plan === p.code}
                  className={cn("p-3 rounded border-2 text-left", plan === p.code ? "border-primary bg-primary/10" : "border-border bg-bg-card")}>
                  <p className="text-xs font-black uppercase text-text-secondary">{p.interval === "annually" ? "Yearly" : "Monthly"}</p>
                  <p className="text-lg font-black text-text">{naira(p.amount_kobo)}</p>
                  <p className="text-[11px] text-text-muted">{p.interval === "annually" ? "per year" : "per month"}</p>
                </button>
              ))}
            </div>
            {token ? (
              <>
                <label className="flex items-start gap-2 text-[11px] text-text-secondary">
                  <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} className="mt-0.5" />
                  <span>Renews automatically until you cancel. Cancelling stops the next renewal; perks last until
                    the paid period ends. Perks from venues and organizers depend on what they offer.</span>
                </label>
                <Button fullWidth disabled={!terms} loading={subscribe.isPending} onClick={() => { setError(""); subscribe.mutate(); }}>
                  Join Turnup+
                </Button>
              </>
            ) : <Link href="/login?next=/plus" className="block text-center text-sm font-bold text-primary underline">Log in to join</Link>}
          </section>
        )}
        {error && <p className="text-xs text-error">{error}</p>}

        <section className="space-y-2">
          <h2 className="text-xs font-black uppercase tracking-widest text-text">What you get</h2>
          {plans.data?.perks.map((p) => (
            <div key={p.id} className="flex gap-3 p-3 rounded border-2 border-border bg-bg-card">
              <Check size={16} className="text-primary shrink-0 mt-0.5" aria-hidden />
              <div><p className="text-sm font-bold text-text">{p.title}</p><p className="text-xs text-text-muted">{p.body}</p></div>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
