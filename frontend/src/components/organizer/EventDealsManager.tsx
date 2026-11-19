"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gift } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage } from "@/lib/api";
import { plusApi, portalApi, type Deal } from "@/lib/marketplace";
import { useAuthStore } from "@/store/auth";

const KINDS = [
  ["free_entry", "Free entry"], ["discount", "Discount"], ["free_item", "Free drink / item"],
  ["reserved", "Reserved table / spot"], ["other", "Other"],
] as const;

/** Turnup+ member deals for an event (organizers) or a venue (venue portal). */
export function DealsEditor({ deals, onCreate, onToggle }: {
  deals: Deal[] | undefined;
  onCreate: (d: Partial<Deal>) => Promise<unknown>;
  onToggle: (d: Deal) => Promise<unknown>;
}) {
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("free_entry");
  const [description, setDescription] = useState("");
  const [validTo, setValidTo] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-2">
      {deals?.map((d) => (
        <div key={d.id} className="flex items-center gap-2 p-2 rounded border-2 border-border bg-bg-card text-sm">
          <span className="flex-1 text-text">{d.title}<span className="block text-[11px] text-text-muted">{d.redemptions ?? 0} used</span></span>
          <Button size="xs" variant="secondary" onClick={() => onToggle(d)}>{d.is_active ? "Pause" : "Resume"}</Button>
        </div>
      ))}
      <form className="space-y-2 p-2 rounded border-2 border-dashed border-border" onSubmit={async (e) => {
        e.preventDefault(); setError(""); setBusy(true);
        try {
          await onCreate({ title, kind, description: description || null, valid_to: validTo ? new Date(validTo).toISOString() : null });
          setTitle(""); setDescription(""); setValidTo("");
        } catch (err) { setError(apiErrorMessage(err, "Couldn't add the deal.")); } finally { setBusy(false); }
      }}>
        <input required minLength={2} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Free entry before 11pm"
          className="w-full h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text" />
        <div className="grid grid-cols-2 gap-2">
          <select value={kind} onChange={(e) => setKind(e.target.value)} className="h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text">
            {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <input type="datetime-local" value={validTo} onChange={(e) => setValidTo(e.target.value)} aria-label="Valid until"
            className="h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text" />
        </div>
        <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Details (optional)"
          className="w-full h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text" />
        <Button type="submit" size="sm" loading={busy}>Add deal</Button>
        {error && <p className="text-xs text-error">{error}</p>}
      </form>
    </div>
  );
}

export function EventDealsManager({ eventId }: { eventId: string }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const key = ["event-deals", "manage", eventId];
  const { data } = useQuery({ queryKey: key, queryFn: () => plusApi.manageEventDeals(token!, eventId), enabled: !!token && !!eventId });
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  return (
    <div className="space-y-2">
      <p className="text-xs font-bold text-text-secondary uppercase tracking-wide flex items-center gap-1.5"><Gift size={13} aria-hidden /> Member deals</p>
      <p className="text-[11px] text-text-muted">Turnup+ members claim a code and show it at the door; scan or type it on the check-in screen.</p>
      <DealsEditor deals={data}
        onCreate={(d) => plusApi.createEventDeal(token!, eventId, d).then(refresh)}
        onToggle={(d) => plusApi.updateEventDeal(token!, eventId, d.id, { ...d, is_active: !d.is_active }).then(refresh)} />
    </div>
  );
}

export function VenueDealsManager({ venueId }: { venueId: string }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const key = ["portal", venueId, "deals"];
  const { data } = useQuery({ queryKey: key, queryFn: () => portalApi.deals(token!, venueId), enabled: !!token });
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const toggle = useMutation({ mutationFn: (d: Deal) => portalApi.updateDeal(token!, venueId, d.id, { ...d, is_active: !d.is_active }), onSuccess: refresh });
  return <DealsEditor deals={data} onCreate={(d) => portalApi.createDeal(token!, venueId, d).then(refresh)} onToggle={(d) => toggle.mutateAsync(d)} />;
}
