"use client";
/** The bottom sheet people register in: choose tickets, add a promo code, answer the
 *  organizer's questions, then pay (or RSVP for an event without tickets). */
import { Minus, Plus, Tag, X as XIcon } from "lucide-react";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/Button";
import { TierPlusBadges } from "@/components/events/EventMarketplace";
import { RegistrationFields } from "@/components/events/RegistrationFields";
import type { PromoCheck, RegistrationAnswers, RegistrationQuestion, TicketTierDetail } from "@/lib/api";
import { cn, formatMoney } from "@/lib/utils";

export interface PromoState {
  input: string;
  setInput: (v: string) => void;
  applied: PromoCheck | null;
  apply: () => void;
  remove: () => void;
  error: string;
  busy: boolean;
}

export function RegisterSheet({
  open, onClose, title, tiers, cart, onQty, promo, questions, answers, onAnswers, missingId,
  refundPolicy, submitLabel, submitting, onSubmit, error,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Tiers on sale. Empty for an RSVP-only event. */
  tiers: TicketTierDetail[];
  cart: Record<string, number>;
  onQty: (tier: TicketTierDetail, qty: number) => void;
  promo: PromoState | null;
  questions: RegistrationQuestion[];
  answers: RegistrationAnswers;
  onAnswers: (a: RegistrationAnswers) => void;
  missingId: string | null;
  refundPolicy?: string | null;
  submitLabel: string;
  submitting: boolean;
  onSubmit: () => void;
  error: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; };
  }, [open, onClose]);

  if (!open) return null;
  const ticketed = tiers.length > 0;
  const hasPaidInCart = tiers.some((t) => t.price > 0 && (cart[t.id] ?? 0) > 0);

  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/60"
      onClick={onClose}>
      <div ref={panelRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="register-sheet-title"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg max-h-[90vh] flex flex-col bg-bg-surface border-2 border-border rounded-t-xl sm:rounded-xl outline-none">
        <div className="flex items-center justify-between px-4 pt-4 pb-3 border-b-2 border-border">
          <div className="min-w-0">
            <p className="text-[10px] font-black uppercase tracking-widest text-primary">
              {ticketed ? "Get tickets" : "Register"}
            </p>
            <h2 id="register-sheet-title" className="text-base font-black text-text truncate">{title}</h2>
          </div>
          <button type="button" aria-label="Close" onClick={onClose}
            className="p-1.5 rounded hover:bg-bg-elevated transition-colors">
            <XIcon size={18} aria-hidden />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
          {ticketed && (
            <section aria-label="Tickets" className="space-y-2">
              {tiers.map((tier) => {
                const available = tier.available;
                const soldOut = available !== null && available <= 0;
                const qty = cart[tier.id] ?? 0;
                const maxQty = Math.min(tier.max_per_order, available ?? 99);
                return (
                  <div key={tier.id} className={cn(
                    "rounded border-2 p-3 flex items-center gap-3",
                    qty > 0 ? "border-primary bg-primary/5" : "border-border",
                    soldOut && "opacity-60",
                  )}>
                    <div className="flex-1 min-w-0">
                      <p className="font-bold text-text text-sm">{tier.name}</p>
                      {tier.description && <p className="text-xs text-text-muted">{tier.description}</p>}
                      <TierPlusBadges tier={tier} />
                      <p className="text-sm font-black mt-0.5 text-primary">
                        {tier.price === 0 ? <span className="text-success">Free</span> : formatMoney(tier.price, tier.currency)}
                        {available !== null && (
                          <span className="ml-2 text-xs font-medium text-text-muted">{soldOut ? "Sold out" : `${available} left`}</span>
                        )}
                      </p>
                    </div>
                    {!soldOut && (
                      <div className="flex items-center gap-2.5 shrink-0">
                        <button type="button" aria-label={`Fewer ${tier.name}`}
                          onClick={() => onQty(tier, Math.max(0, qty - 1))} disabled={qty === 0}
                          className="w-8 h-8 rounded border-2 border-border flex items-center justify-center hover:border-primary transition-colors disabled:opacity-40">
                          <Minus size={13} aria-hidden />
                        </button>
                        <span className="font-black text-text w-5 text-center" aria-live="polite">{qty}</span>
                        <button type="button" aria-label={`More ${tier.name}`}
                          onClick={() => onQty(tier, Math.min(maxQty, qty + 1))} disabled={qty >= maxQty}
                          className="w-8 h-8 rounded border-2 border-border flex items-center justify-center hover:border-primary transition-colors disabled:opacity-40">
                          <Plus size={13} aria-hidden />
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </section>
          )}

          {ticketed && promo && hasPaidInCart && (
            <section aria-label="Promo code">
              {promo.applied ? (
                <div className="flex items-center justify-between gap-2 rounded border-2 border-success/50 bg-success/5 px-3 py-2">
                  <span className="flex items-center gap-1.5 text-sm font-bold text-success">
                    <Tag size={14} aria-hidden /> {promo.applied.code}
                    <span className="font-medium">
                      · {promo.applied.discount_type === "percent"
                        ? `${promo.applied.discount_value}% off`
                        : `${formatMoney(promo.applied.discount, "NGN")} off`}
                    </span>
                  </span>
                  <button type="button" onClick={promo.remove} className="text-xs font-bold text-text-muted hover:text-text">Remove</button>
                </div>
              ) : (
                <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); promo.apply(); }}>
                  <label htmlFor="promo-code" className="sr-only">Promo code</label>
                  <input id="promo-code" value={promo.input} autoCapitalize="characters" autoComplete="off"
                    onChange={(e) => promo.setInput(e.target.value)} placeholder="Promo code" maxLength={40}
                    className="flex-1 h-10 rounded border-2 border-border bg-bg px-3 text-sm text-text uppercase placeholder:normal-case placeholder:text-text-muted focus:outline-none focus:border-primary" />
                  <Button type="submit" variant="secondary" loading={promo.busy} disabled={!promo.input.trim()}>Apply</Button>
                </form>
              )}
              {promo.error && <p className="text-xs text-error mt-1.5">{promo.error}</p>}
            </section>
          )}

          {questions.length > 0 && (
            <section aria-labelledby="questions-heading" className="space-y-3">
              <h3 id="questions-heading" className="text-xs font-black uppercase tracking-widest text-text-secondary">
                A few questions from the host
              </h3>
              <RegistrationFields questions={questions} answers={answers} onChange={onAnswers} missingId={missingId} />
            </section>
          )}

          {refundPolicy && ticketed && <p className="text-xs text-text-muted">{refundPolicy}</p>}
        </div>

        <div className="px-4 pt-3 pb-4 border-t-2 border-border safe-pb space-y-2">
          {ticketed && promo?.applied && (
            <div className="flex justify-between text-sm text-text-muted">
              <span>Subtotal <s>{formatMoney(promo.applied.subtotal, "NGN")}</s></span>
              <span className="text-success font-bold">−{formatMoney(promo.applied.discount, "NGN")}</span>
            </div>
          )}
          <Button fullWidth size="lg" loading={submitting} onClick={onSubmit}>{submitLabel}</Button>
          {error && <p role="alert" className="text-xs text-error text-center">{error}</p>}
        </div>
      </div>
    </div>
  );
}
