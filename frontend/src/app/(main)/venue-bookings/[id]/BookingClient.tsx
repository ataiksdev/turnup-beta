"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Download, Phone } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage } from "@/lib/api";
import {
  BOOKING_STATUS, REFUND_STATUS, bookingsApi, downloadWithAuth, goToPayment, naira, paymentCallback,
  type CancelPreview,
} from "@/lib/marketplace";
import { routes } from "@/lib/routes";
import { useRouteParam } from "@/lib/useRouteParam";
import { useAuthStore } from "@/store/auth";

const DISPUTE_REASONS = [
  ["not_as_listed", "Not as listed"], ["venue_no_show", "Venue didn't provide the space"],
  ["damage", "Damage claim"], ["other", "Something else"],
] as const;

export function BookingClient() {
  const id = useRouteParam("id");
  const { token, hasHydrated } = useAuthStore();
  const qc = useQueryClient();
  const [error, setError] = useState("");
  const [amount, setAmount] = useState("");
  const [preview, setPreview] = useState<CancelPreview | null>(null);
  const [reason, setReason] = useState("");
  const [disputeOpen, setDisputeOpen] = useState(false);
  const [dReason, setDReason] = useState("not_as_listed");
  const [dText, setDText] = useState("");
  const [rating, setRating] = useState(5);
  const [reviewText, setReviewText] = useState("");
  const [reviewed, setReviewed] = useState(false);

  const { data: b } = useQuery({
    queryKey: ["venue-booking", id], queryFn: () => bookingsApi.booking(token!, id), enabled: hasHydrated && !!token && !!id,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["venue-booking", id] });
  const fail = (fallback: string) => (err: unknown) => setError(apiErrorMessage(err, fallback));

  const pay = useMutation({
    mutationFn: () => bookingsApi.pay(token!, id, amount ? Math.round(Number(amount) * 100) : null, paymentCallback(routes.venueBooking(id))),
    onSuccess: goToPayment, onError: fail("Couldn't start the payment."),
  });
  const cancelPreview = useMutation({
    mutationFn: () => bookingsApi.cancel(token!, id, true), onSuccess: setPreview, onError: fail("Couldn't check the refund."),
  });
  const cancel = useMutation({
    mutationFn: () => bookingsApi.cancel(token!, id, false, reason), onSuccess: () => { setPreview(null); refresh(); },
    onError: fail("Couldn't cancel."),
  });
  const dispute = useMutation({
    mutationFn: () => bookingsApi.dispute(token!, id, { reason: dReason, description: dText }),
    onSuccess: () => { setDisputeOpen(false); refresh(); }, onError: fail("Couldn't open the dispute."),
  });
  const review = useMutation({
    mutationFn: () => bookingsApi.review(token!, id, rating, reviewText || undefined),
    onSuccess: () => setReviewed(true), onError: fail("Couldn't save the review."),
  });

  if (!b) return <div><TopBar back title="Booking" /><div className="m-4 h-40 rounded border-2 border-border bg-bg-card animate-pulse" /></div>;
  const live = ["confirmed", "fully_paid"].includes(b.status);

  return (
    <div className="pb-24">
      <TopBar back title="Venue booking" />
      <div className="px-4 py-4 space-y-4">
        <section className="p-4 rounded border-2 border-border bg-bg-card space-y-1">
          <p className="text-[10px] font-black uppercase text-primary">{BOOKING_STATUS[b.status] ?? b.status}</p>
          <Link href={routes.venue(b.venue.slug)} className="text-lg font-black text-text hover:text-primary">{b.venue.name}</Link>
          <p className="text-sm text-text-secondary">{b.space.name}</p>
          <p className="text-sm text-text">{format(new Date(b.starts_at), "EEE d MMM yyyy, h:mm a")} – {format(new Date(b.ends_at), "h:mm a")}</p>
          {b.venue.address && <p className="text-xs text-text-secondary">{b.venue.address}</p>}
          {b.venue.phone && <a href={`tel:${b.venue.phone}`} className="text-xs font-bold text-primary flex items-center gap-1"><Phone size={12} aria-hidden /> {b.venue.phone}</a>}
          <Link href={routes.enquiry(b.enquiry_id)} className="text-xs font-bold text-primary underline">Messages</Link>
        </section>

        <section className="p-4 rounded border-2 border-border bg-bg-card space-y-2 text-sm">
          <div className="flex justify-between"><span className="text-text-muted">Total</span><span className="font-black text-text">{naira(b.total_kobo)}</span></div>
          <div className="flex justify-between"><span className="text-text-muted">Paid through Turnup</span><span className="font-bold text-text">{naira(b.paid_kobo)}</span></div>
          {b.refunded_kobo > 0 && <div className="flex justify-between"><span className="text-text-muted">Refunded</span><span className="text-text">{naira(b.refunded_kobo)}</span></div>}
          {b.status === "confirmed" && b.balance_kobo > 0 && (
            <div className="pt-2 border-t-2 border-border-subtle space-y-2">
              <p className="text-xs text-text-secondary">Balance {naira(b.balance_kobo)} due by {format(new Date(b.balance_due_at), "d MMM yyyy")}. You can pay in parts.</p>
              <div className="flex gap-2">
                <input type="number" min={1000} placeholder={`Full balance (${naira(b.balance_kobo)})`} value={amount}
                  onChange={(e) => setAmount(e.target.value)} aria-label="Amount in naira"
                  className="flex-1 h-10 rounded border-2 border-border bg-bg px-3 text-sm text-text" />
                <Button loading={pay.isPending} onClick={() => { setError(""); pay.mutate(); }}>Pay</Button>
              </div>
            </div>
          )}
          <p className="text-[11px] text-text-muted">{b.refund_policy}. Refunds are paid by the venue and passed on by Turnup.</p>
        </section>

        {b.refund_requests.map((r) => (
          <section key={r.id} className="p-4 rounded border-2 border-primary/50 bg-bg-card space-y-2">
            <p className="text-xs font-black uppercase text-text">Refund of {naira(r.amount_kobo)}</p>
            <p className="text-sm text-text-secondary">{REFUND_STATUS[r.status] ?? r.status}</p>
            <p className="text-xs text-text-muted">Received {naira(r.refunded_kobo)} so far.
              {r.status === "awaiting_venue" && ` The venue must pay it in by ${format(new Date(r.due_at), "d MMM, h:mm a")}.`}</p>
            {r.status === "referred" && (
              <Button size="sm" variant="secondary" onClick={() => downloadWithAuth(token!, bookingsApi.claimPackUrl(r.id), `turnup-claim-${r.id.slice(0, 8)}.pdf`).catch(fail("Couldn't download it."))}>
                <Download size={14} aria-hidden /> Download claim pack
              </Button>
            )}
            {["overdue", "suspended", "referred"].includes(r.status) && !r.settled_by_organizer && (
              <button className="text-xs font-bold text-text-secondary underline"
                onClick={() => bookingsApi.settled(token!, r.id).then(refresh).catch(fail("Couldn't update it."))}>
                {r.settled_by_venue ? "The venue says it paid you directly. Confirm" : "I've been paid directly"}
              </button>
            )}
          </section>
        ))}

        {b.disputes.map((d) => (
          <section key={d.id} className="p-4 rounded border-2 border-border bg-bg-card space-y-1 text-sm">
            <p className="text-xs font-black uppercase text-text">Dispute · {d.status}</p>
            <p className="text-text-secondary">{d.description}</p>
            {d.resolution && <p className="text-text">Decision: {d.resolution.replace("_", " ")}{d.refund_kobo ? `, ${naira(d.refund_kobo)}` : ""}. {d.decision_note}</p>}
          </section>
        ))}

        {live && (
          <section className="space-y-2">
            {!preview ? (
              <Button variant="ghost" size="sm" loading={cancelPreview.isPending} onClick={() => cancelPreview.mutate()}>Cancel booking</Button>
            ) : (
              <div className="p-3 rounded border-2 border-error/50 space-y-2">
                <p className="text-sm text-text">You'd get {naira(preview.refund_kobo)} back ({preview.refund_percent}% of {naira(preview.paid_kobo)}), paid by the venue.</p>
                <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional)"
                  className="w-full h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text" />
                <div className="flex gap-2">
                  <Button variant="danger" size="sm" loading={cancel.isPending} onClick={() => cancel.mutate()}>Confirm cancellation</Button>
                  <Button variant="ghost" size="sm" onClick={() => setPreview(null)}>Keep booking</Button>
                </div>
              </div>
            )}
            {!disputeOpen ? (
              <Button variant="ghost" size="sm" onClick={() => setDisputeOpen(true)}>Report a problem</Button>
            ) : (
              <div className="p-3 rounded border-2 border-border space-y-2">
                <select value={dReason} onChange={(e) => setDReason(e.target.value)}
                  className="w-full h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text">
                  {DISPUTE_REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
                <textarea value={dText} onChange={(e) => setDText(e.target.value)} rows={3} placeholder="What happened?"
                  className="w-full rounded border-2 border-border bg-bg px-2 py-1 text-sm text-text" />
                <p className="text-[11px] text-text-muted">A Turnup admin reviews the messages and evidence and decides. Any refund is paid by the venue.</p>
                <Button size="sm" loading={dispute.isPending} disabled={dText.trim().length < 10} onClick={() => dispute.mutate()}>Open dispute</Button>
              </div>
            )}
          </section>
        )}

        {b.status === "completed" && !reviewed && (
          <section className="p-4 rounded border-2 border-border bg-bg-card space-y-2">
            <p className="text-xs font-black uppercase text-text">Review the venue</p>
            <div className="flex gap-1" role="radiogroup" aria-label="Rating">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} role="radio" aria-checked={rating === n} onClick={() => setRating(n)}
                  className={n <= rating ? "text-warning text-xl" : "text-text-muted text-xl"}>★</button>
              ))}
            </div>
            <textarea value={reviewText} onChange={(e) => setReviewText(e.target.value)} rows={3}
              className="w-full rounded border-2 border-border bg-bg px-2 py-1 text-sm text-text" />
            <Button size="sm" loading={review.isPending} onClick={() => review.mutate()}>Post review</Button>
          </section>
        )}
        {reviewed && <p className="text-sm text-success font-bold">Thanks for your review.</p>}
        {error && <p className="text-xs text-error">{error}</p>}
      </div>
    </div>
  );
}
