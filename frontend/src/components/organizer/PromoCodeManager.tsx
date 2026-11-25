"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Tag, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage, eventsApi, type PromoCode } from "@/lib/api";
import { cn, formatMoney } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";

const field = "h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text";

function describe(p: PromoCode): string {
  return p.discount_type === "percent"
    ? `${p.discount_value}% off`
    : `${formatMoney(p.discount_value, "NGN")} off the order`;
}

/** Discount codes for one event. The organizer absorbs the discount. */
export function PromoCodeManager({ eventId }: { eventId: string }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const key = ["promo-codes", eventId];
  const { data: codes } = useQuery({
    queryKey: key, queryFn: () => eventsApi.promoCodes(token!, eventId), enabled: !!token && !!eventId,
  });
  const { data: tiers } = useQuery({
    queryKey: ["manage-tiers", eventId], queryFn: () => eventsApi.manageTiers(token!, eventId),
    enabled: !!token && !!eventId,
  });
  const paidTiers = (tiers ?? []).filter((t) => t.price > 0);
  const refresh = () => qc.invalidateQueries({ queryKey: key });

  const [code, setCode] = useState("");
  const [type, setType] = useState<"percent" | "amount">("percent");
  const [value, setValue] = useState("");
  const [maxUses, setMaxUses] = useState("");
  const [until, setUntil] = useState("");
  const [tierIds, setTierIds] = useState<string[]>([]);
  const [error, setError] = useState("");

  const create = useMutation({
    mutationFn: () => eventsApi.createPromoCode(token!, eventId, {
      code: code.trim(), discount_type: type, discount_value: Number(value),
      max_uses: maxUses ? Number(maxUses) : null,
      valid_until: until ? new Date(until).toISOString() : null,
      tier_ids: tierIds.length ? tierIds : null,
    }),
    onSuccess: () => {
      setCode(""); setValue(""); setMaxUses(""); setUntil(""); setTierIds([]); setError("");
      refresh();
    },
    onError: (err) => setError(apiErrorMessage(err, "Couldn't add the code.")),
  });
  const toggle = useMutation({
    mutationFn: (p: PromoCode) => eventsApi.updatePromoCode(token!, eventId, p.id, { is_active: !p.is_active }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (p: PromoCode) => eventsApi.deletePromoCode(token!, eventId, p.id),
    onSuccess: refresh,
    onError: (err) => setError(apiErrorMessage(err, "Couldn't delete the code.")),
  });

  return (
    <div className="space-y-2">
      <p className="text-xs font-bold text-text-secondary uppercase tracking-wide flex items-center gap-1.5">
        <Tag size={13} aria-hidden /> Promo codes
      </p>
      <p className="text-[11px] text-text-muted">
        Buyers enter a code at checkout. You absorb the discount; Turnup&apos;s fee is on what they actually pay.
      </p>

      {codes?.map((p) => (
        <div key={p.id} className={cn("flex items-center gap-2 p-2 rounded border-2 border-border bg-bg-card text-sm",
          !p.is_active && "opacity-60")}>
          <div className="flex-1 min-w-0">
            <p className="font-mono font-black text-text">{p.code}</p>
            <p className="text-[11px] text-text-muted">
              {describe(p)}
              {p.tier_ids?.length ? ` · ${p.tier_ids.length} ticket type${p.tier_ids.length > 1 ? "s" : ""}` : ""}
              {" · "}{p.times_used}{p.max_uses ? `/${p.max_uses}` : ""} used
              {p.discount_given > 0 && ` · ${formatMoney(p.discount_given, "NGN")} given`}
              {p.valid_until && ` · until ${new Date(p.valid_until).toLocaleDateString()}`}
            </p>
          </div>
          <Button size="xs" variant="secondary" onClick={() => toggle.mutate(p)}>{p.is_active ? "Turn off" : "Turn on"}</Button>
          {p.times_used === 0 && (
            <button type="button" aria-label={`Delete ${p.code}`} onClick={() => remove.mutate(p)}
              className="p-1.5 rounded text-text-muted hover:text-error hover:bg-bg-elevated">
              <Trash2 size={14} aria-hidden />
            </button>
          )}
        </div>
      ))}

      <form className="space-y-2 p-2 rounded border-2 border-dashed border-border"
        onSubmit={(e) => { e.preventDefault(); setError(""); create.mutate(); }}>
        <div className="grid grid-cols-2 gap-2">
          <input required pattern="[A-Za-z0-9_\-]{3,40}" title="3-40 letters, numbers, - or _"
            value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="CODE e.g. EARLYBIRD" aria-label="Code" className={cn(field, "font-mono uppercase")} />
          <div className="flex gap-1">
            <input required type="number" min="1" max={type === "percent" ? 100 : undefined} step="any"
              value={value} onChange={(e) => setValue(e.target.value)}
              placeholder={type === "percent" ? "20" : "2000"} aria-label="Discount" className={cn(field, "w-full")} />
            <select value={type} onChange={(e) => setType(e.target.value as "percent" | "amount")}
              aria-label="Discount type" className={field}>
              <option value="percent">% off</option>
              <option value="amount">₦ off</option>
            </select>
          </div>
          <input type="number" min="1" value={maxUses} onChange={(e) => setMaxUses(e.target.value)}
            placeholder="Max uses (blank = no limit)" aria-label="Maximum uses" className={field} />
          <input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)}
            aria-label="Valid until" title="Valid until" className={field} />
        </div>
        {paidTiers.length > 1 && (
          <fieldset>
            <legend className="text-[11px] text-text-muted mb-1">Only for (leave all off for every ticket type):</legend>
            <div className="flex flex-wrap gap-1.5">
              {paidTiers.map((t) => {
                const on = tierIds.includes(t.id);
                return (
                  <button key={t.id} type="button" aria-pressed={on}
                    onClick={() => setTierIds(on ? tierIds.filter((x) => x !== t.id) : [...tierIds, t.id])}
                    className={cn("px-2 py-1 rounded border-2 text-xs font-semibold",
                      on ? "border-primary bg-primary/10 text-primary" : "border-border text-text")}>
                    {t.name}
                  </button>
                );
              })}
            </div>
          </fieldset>
        )}
        <Button type="submit" size="sm" loading={create.isPending}>Add code</Button>
        {error && <p className="text-xs text-error">{error}</p>}
      </form>
    </div>
  );
}
