"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, Pencil, Play, Trash2 } from "lucide-react";
import { apiErrorMessage, eventsApi, type TicketTierDetail } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/utils";

function toLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

const naira = (n: number) => (n === 0 ? "Free" : `₦${n.toLocaleString("en-NG", { maximumFractionDigits: 2 })}`);

function TierRow({ eventId, tier }: { eventId: string; tier: TicketTierDetail }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(tier.name);
  const [price, setPrice] = useState(String(tier.price));
  const [quantity, setQuantity] = useState(tier.quantity === null ? "" : String(tier.quantity));
  // Turnup+ options (docs/venues-spec.md 4.8)
  const [membersOnly, setMembersOnly] = useState(!!tier.members_only);
  const [presaleUntil, setPresaleUntil] = useState(toLocal(tier.plus_presale_ends_at));
  const [presaleThen, setPresaleThen] = useState<"open" | "close">(tier.presale_then ?? "open");
  const [error, setError] = useState("");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["manage-tiers", eventId] });
    qc.invalidateQueries({ queryKey: ["tiers", eventId] });
  };
  const update = useMutation({
    mutationFn: (data: Parameters<typeof eventsApi.updateTier>[3]) => eventsApi.updateTier(token!, eventId, tier.id, data),
    onSuccess: () => { setEditing(false); setError(""); refresh(); },
    onError: (e) => setError(apiErrorMessage(e, "Could not update this tier.")),
  });
  const remove = useMutation({
    mutationFn: () => eventsApi.deleteTier(token!, eventId, tier.id),
    onSuccess: refresh,
    onError: (e) => setError(apiErrorMessage(e, "Could not delete this tier.")),
  });

  function save(e: React.FormEvent) {
    e.preventDefault();
    const p = Number(price);
    const q = quantity.trim() === "" ? null : Number(quantity);
    if (!name.trim()) return setError("Give the tier a name.");
    if (isNaN(p) || p < 0) return setError("Enter a valid price.");
    if (q !== null && (!Number.isInteger(q) || q < 1)) return setError("Quantity must be a whole number, or blank for unlimited.");
    update.mutate({
      name: name.trim(), price: p, quantity: q, members_only: membersOnly,
      plus_presale_ends_at: presaleUntil ? new Date(presaleUntil).toISOString() : null, presale_then: presaleThen,
    });
  }

  return (
    <div className={cn("p-3 rounded border-2 border-border bg-bg-card space-y-2", !tier.is_active && "opacity-70")}>
      {!editing ? (
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-black text-text truncate">{tier.name}</p>
            <p className="text-xs text-text-muted">
              {naira(tier.price)} · {tier.quantity_sold} sold
              {tier.quantity !== null ? ` of ${tier.quantity}` : " · unlimited"}
              {!tier.is_active && " · sales paused"}
            </p>
            {(tier.members_only || tier.plus_presale_ends_at) && (
              <p className="text-[10px] font-black uppercase text-primary">
                {tier.members_only ? "Turnup+ members only" : `Members' presale until ${new Date(tier.plus_presale_ends_at!).toLocaleString()}`}
              </p>
            )}
          </div>
          <div className="flex gap-1 shrink-0">
            <Button type="button" size="xs" variant="secondary" aria-label={`Edit ${tier.name}`} onClick={() => setEditing(true)}>
              <Pencil size={12} />
            </Button>
            <Button type="button" size="xs" variant="secondary" loading={update.isPending}
              aria-label={tier.is_active ? `Pause sales of ${tier.name}` : `Resume sales of ${tier.name}`}
              onClick={() => update.mutate({ is_active: !tier.is_active })}>
              {tier.is_active ? <Pause size={12} /> : <Play size={12} />}
            </Button>
            {tier.quantity_sold === 0 && (
              <Button type="button" size="xs" variant="danger" loading={remove.isPending} aria-label={`Delete ${tier.name}`}
                onClick={() => { if (confirm(`Delete the "${tier.name}" tier?`)) remove.mutate(); }}>
                <Trash2 size={12} />
              </Button>
            )}
          </div>
        </div>
      ) : (
        <form onSubmit={save} className="space-y-2">
          <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <div className="grid grid-cols-2 gap-2">
            <Input label="Price (₦)" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
            <Input label="Quantity" inputMode="numeric" placeholder="Unlimited" value={quantity}
              onChange={(e) => setQuantity(e.target.value)} />
          </div>
          <fieldset className="p-2 rounded border-2 border-border-subtle space-y-2">
            <legend className="px-1 text-[10px] font-black uppercase text-primary">Turnup+</legend>
            <label className="flex items-center gap-2 text-xs text-text">
              <input type="checkbox" checked={membersOnly} onChange={(e) => setMembersOnly(e.target.checked)} />
              Members only (a members' guest list)
            </label>
            {!membersOnly && (
              <div className="grid grid-cols-2 gap-2">
                <label className="text-[11px] font-bold uppercase text-text-secondary space-y-1">Members' presale until
                  <input type="datetime-local" value={presaleUntil} onChange={(e) => setPresaleUntil(e.target.value)}
                    className="w-full h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text normal-case" />
                </label>
                <label className="text-[11px] font-bold uppercase text-text-secondary space-y-1">Then
                  <select value={presaleThen} onChange={(e) => setPresaleThen(e.target.value as "open" | "close")}
                    className="w-full h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text normal-case">
                    <option value="open">Open to everyone</option>
                    <option value="close">Stop selling</option>
                  </select>
                </label>
              </div>
            )}
          </fieldset>
          {tier.quantity_sold > 0 && (
            <p className="text-[11px] text-text-muted">
              {tier.quantity_sold} already sold: price changes apply to new sales only.
            </p>
          )}
          <div className="flex gap-2">
            <Button type="submit" size="sm" loading={update.isPending}>Save</Button>
            <Button type="button" size="sm" variant="secondary" onClick={() => { setEditing(false); setError(""); }}>Cancel</Button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="text-xs text-error">{error}</p>}
    </div>
  );
}

/** Edit, pause/resume or delete an event's existing ticket tiers (host/co-host view). */
export function TierManager({ eventId }: { eventId: string }) {
  const { token } = useAuthStore();
  const { data: tiers } = useQuery({
    queryKey: ["manage-tiers", eventId],
    queryFn: () => eventsApi.manageTiers(token!, eventId),
    enabled: !!token && !!eventId,
  });
  if (!tiers || tiers.length === 0) return null;
  return (
    <div className="space-y-2">
      <p className="text-xs font-bold text-text-secondary uppercase tracking-wide">Ticket Tiers</p>
      {tiers.map((t) => <TierRow key={t.id} eventId={eventId} tier={t} />)}
      <p className="text-[10px] text-text-muted">Tiers with sales can be paused but not deleted.</p>
    </div>
  );
}
