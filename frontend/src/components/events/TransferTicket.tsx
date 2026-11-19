"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage } from "@/lib/api";
import { isPlus, plusApi } from "@/lib/marketplace";
import { useAuthStore } from "@/store/auth";

/** Turnup+ perk: send this ticket to another Turnup user (the old QR code stops working). */
export function TransferTicket({ orderId }: { orderId: string }) {
  const { token, user } = useAuthStore();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  if (done) return <p className="text-sm font-bold text-success text-center">Sent to @{done}. This ticket is now theirs.</p>;
  if (!isPlus(user)) {
    return <p className="text-xs text-text-muted text-center">Can't go? <Link href="/plus" className="text-primary font-bold underline">Turnup+</Link> members can send their ticket to a friend.</p>;
  }
  if (!open) return <Button variant="secondary" fullWidth onClick={() => setOpen(true)}><Send size={14} aria-hidden /> Send to a friend</Button>;
  return (
    <form className="p-3 rounded border-2 border-border bg-bg-card space-y-2" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setError("");
      try {
        const r = await plusApi.transfer(token!, orderId, to);
        setDone(r.to);
        qc.invalidateQueries({ queryKey: ["my-tickets"] });
      } catch (err) { setError(apiErrorMessage(err, "Couldn't send the ticket.")); } finally { setBusy(false); }
    }}>
      <label className="block text-xs font-bold uppercase text-text-secondary">Their Turnup username
        <input required value={to} onChange={(e) => setTo(e.target.value)} placeholder="@username"
          className="mt-1 w-full h-10 rounded border-2 border-border bg-bg px-3 text-sm text-text normal-case" />
      </label>
      <p className="text-[11px] text-text-muted">Your QR code stops working and they get a new one. This can't be undone.</p>
      <Button type="submit" size="sm" loading={busy}>Send ticket</Button>
      {error && <p className="text-xs text-error">{error}</p>}
    </form>
  );
}
