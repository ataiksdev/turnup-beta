"use client";
import { format } from "date-fns";
import { AlertTriangle, FileText, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { naira, type Enquiry, type Message, type Quote } from "@/lib/marketplace";
import { cn } from "@/lib/utils";

function when(d: string) {
  return format(new Date(d), "EEE d MMM, h:mm a");
}

export function QuoteCard({ quote, spaceName, actions }: {
  quote: Quote; spaceName?: string; actions?: React.ReactNode;
}) {
  const open = quote.status === "sent";
  return (
    <div className={cn("rounded border-2 bg-bg-card p-3 space-y-2 shadow-brutal-sm",
      open ? "border-primary" : "border-border opacity-80")}>
      <div className="flex items-center gap-2">
        <FileText size={14} className="text-primary" aria-hidden />
        <span className="text-xs font-black uppercase tracking-wide text-text">Quote</span>
        <span className="ml-auto text-[10px] font-bold uppercase text-text-muted">{quote.status}</span>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        {spaceName && <><dt className="text-text-muted">Space</dt><dd className="text-text font-bold">{spaceName}</dd></>}
        <dt className="text-text-muted">From</dt><dd className="text-text">{when(quote.starts_at)}</dd>
        <dt className="text-text-muted">To</dt><dd className="text-text">{when(quote.ends_at)}</dd>
        <dt className="text-text-muted">Total</dt><dd className="text-text font-black">{naira(quote.total_kobo)}</dd>
        <dt className="text-text-muted">Deposit now</dt><dd className="text-text font-bold">{naira(quote.deposit_kobo)}</dd>
        <dt className="text-text-muted">Balance</dt>
        <dd className="text-text">{naira(quote.balance_kobo)}, due {quote.balance_due_days} days before</dd>
        <dt className="text-text-muted">Valid until</dt><dd className="text-text">{when(quote.valid_until)}</dd>
      </dl>
      {quote.inclusions && <p className="text-xs text-text-secondary whitespace-pre-wrap">{quote.inclusions}</p>}
      <p className="text-[11px] text-text-muted">{quote.refund_policy}</p>
      {open && actions}
    </div>
  );
}

export function EnquiryThread({ enquiry, side, onSend, quoteActions, sending }: {
  enquiry: Enquiry; side: "organizer" | "venue"; onSend?: (body: string) => Promise<void>;
  quoteActions?: (q: Quote) => React.ReactNode; sending?: boolean;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);
  // Block body: newer browsers return a Promise from scrollIntoView, and an effect must
  // return nothing or a cleanup function.
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [enquiry.messages?.length]);
  const closed = ["closed", "expired", "declined"].includes(enquiry.status);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || !onSend) return;
    setError("");
    try {
      await onSend(text.trim());
      setText("");
    } catch (err: any) {
      setError(err?.message ?? "Couldn't send. Try again.");
    }
  }

  return (
    <div className="space-y-3">
      <ol className="space-y-2" aria-label="Messages">
        {enquiry.messages?.map((m: Message) => {
          const mine = m.sender_side === side;
          if (m.sender_side === "system") {
            return <li key={m.id} className="text-center text-[11px] text-text-muted">{m.body}</li>;
          }
          return (
            <li key={m.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
              <div className="max-w-[88%] space-y-1">
                {m.quote ? (
                  <QuoteCard quote={m.quote} spaceName={enquiry.space?.name ?? undefined}
                    actions={quoteActions?.(m.quote)} />
                ) : (
                  <div className={cn("rounded px-3 py-2 text-sm border-2",
                    mine ? "bg-primary/10 border-primary/40 text-text" : "bg-bg-card border-border text-text")}>
                    <p className="whitespace-pre-wrap break-words">{m.body}</p>
                  </div>
                )}
                {m.flagged_contact && (
                  <p className="flex items-center gap-1 text-[10px] text-warning font-bold">
                    <AlertTriangle size={11} aria-hidden />
                    Payments made outside Turnup aren't covered by the booking terms.
                  </p>
                )}
                <p className={cn("text-[10px] text-text-muted", mine && "text-right")}>{when(m.created_at)}</p>
              </div>
            </li>
          );
        })}
        <div ref={end} />
      </ol>
      {onSend && !closed && (
        <form onSubmit={send} className="flex gap-2 sticky bottom-20 bg-bg py-2">
          <textarea
            value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={4000}
            aria-label="Message" placeholder="Write a message"
            className="flex-1 rounded border-2 border-border bg-bg-card px-3 py-2 text-sm text-text focus:outline-none focus:border-primary"
          />
          <Button type="submit" loading={sending} disabled={!text.trim()} aria-label="Send"><Send size={16} /></Button>
        </form>
      )}
      {error && <p className="text-xs text-error">{error}</p>}
      {closed && <p className="text-xs text-text-muted text-center">This conversation is closed.</p>}
    </div>
  );
}
