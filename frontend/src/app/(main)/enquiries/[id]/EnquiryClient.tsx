"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Flag, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { EnquiryThread } from "@/components/venues/EnquiryThread";
import { apiErrorMessage } from "@/lib/api";
import { bookingsApi, goToPayment, paymentCallback, type Quote } from "@/lib/marketplace";
import { routes } from "@/lib/routes";
import { useRouteParam } from "@/lib/useRouteParam";
import { useAuthStore } from "@/store/auth";

export function EnquiryClient() {
  const id = useRouteParam("id");
  const { token, hasHydrated } = useAuthStore();
  const qc = useQueryClient();
  const [error, setError] = useState("");
  const [terms, setTerms] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [reportText, setReportText] = useState("");
  const [reported, setReported] = useState(false);

  const { data: e } = useQuery({
    queryKey: ["enquiry", id], queryFn: () => bookingsApi.enquiry(token!, id),
    enabled: hasHydrated && !!token && !!id, refetchInterval: 20_000,
  });
  const send = useMutation({
    mutationFn: (body: string) => bookingsApi.message(token!, id, body),
    onSuccess: (data) => qc.setQueryData(["enquiry", id], data),
  });
  const accept = useMutation({
    mutationFn: (q: Quote) => bookingsApi.acceptQuote(token!, q.id, paymentCallback(routes.enquiry(id))),
    onSuccess: goToPayment,
    onError: (err) => setError(apiErrorMessage(err, "Couldn't start the payment.")),
  });
  const decline = useMutation({
    mutationFn: (q: Quote) => bookingsApi.declineQuote(token!, q.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enquiry", id] }),
  });

  if (!e) return <div><TopBar back title="Enquiry" /><div className="m-4 h-40 rounded border-2 border-border bg-bg-card animate-pulse" /></div>;

  return (
    <div className="pb-28">
      <TopBar back title={e.venue.name} />
      <div className="px-4 py-3 space-y-3">
        <div className="p-3 rounded border-2 border-border bg-bg-card text-xs text-text-secondary space-y-0.5">
          <p><span className="font-bold text-text">{format(new Date(e.starts_at), "EEE d MMM yyyy, h:mm a")}</span> to {format(new Date(e.ends_at), "h:mm a")}</p>
          <p>{e.guest_count} guests{e.space ? ` · ${e.space.name}` : ""}{e.event_type ? ` · ${e.event_type}` : ""}</p>
          <Link href={routes.venue(e.venue.slug)} className="text-primary font-bold underline">View venue</Link>
          {e.booking_id && (
            <Link href={routes.venueBooking(e.booking_id)} className="ml-3 text-primary font-bold underline">View booking</Link>
          )}
        </div>

        <EnquiryThread
          enquiry={e} side="organizer" sending={send.isPending}
          onSend={async (body) => { await send.mutateAsync(body); }}
          quoteActions={(q) => (
            <div className="space-y-2 pt-1">
              {!e.venue.deposits_enabled && (
                <p className="text-[11px] text-warning font-bold">Payment opens once Turnup has visited this venue.</p>
              )}
              <label className="flex items-start gap-2 text-[11px] text-text-secondary">
                <input type="checkbox" checked={terms} onChange={(ev) => setTerms(ev.target.checked)} className="mt-0.5" />
                <span>I agree to the booking policy: my contract is with the venue; Turnup collects payment for the
                  venue; refunds are owed and paid by the venue and passed on by Turnup, which enforces penalties
                  on the venue but doesn't pay refunds itself. Only payments made through Turnup are covered.</span>
              </label>
              <div className="flex gap-2">
                <Button size="sm" disabled={!terms || !e.venue.deposits_enabled} loading={accept.isPending}
                  onClick={() => { setError(""); accept.mutate(q); }}>
                  Accept and pay deposit
                </Button>
                <Button size="sm" variant="ghost" loading={decline.isPending} onClick={() => decline.mutate(q)}>Decline</Button>
              </div>
            </div>
          )}
        />
        {error && <p className="text-xs text-error">{error}</p>}

        <div className="p-3 rounded border-2 border-border-subtle text-[11px] text-text-muted space-y-2">
          <p className="flex items-start gap-1.5"><ShieldCheck size={13} className="shrink-0 text-primary" aria-hidden />
            Pay the deposit and the balance through Turnup: refunds, disputes and the venue's penalties only apply to
            money paid here, and full payments count towards your Trusted organizer badge.</p>
          {reported ? <p className="font-bold text-success">Thanks. Turnup will review it.</p> : reporting ? (
            <div className="space-y-2">
              <textarea value={reportText} onChange={(ev) => setReportText(ev.target.value)} rows={2} maxLength={2000}
                placeholder="What did the venue ask for?"
                className="w-full rounded border-2 border-border bg-bg px-2 py-1 text-xs text-text" />
              <Button size="xs" variant="secondary" onClick={async () => {
                await bookingsApi.report(token!, id, reportText);
                setReported(true);
              }}>Send report</Button>
            </div>
          ) : (
            <button onClick={() => setReporting(true)} className="flex items-center gap-1 font-bold text-text-secondary underline">
              <Flag size={12} aria-hidden /> The venue asked me to pay outside Turnup
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
