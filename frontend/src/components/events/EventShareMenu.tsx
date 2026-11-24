"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Copy, MessageCircle, Share2 } from "lucide-react";
import { shareApi, type ShareChannel } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { cn, copyToClipboard } from "@/lib/utils";

/** Share an event on WhatsApp, the phone's share sheet, or by copying the link. Signed in,
 *  the link carries your ref code, so you get credit for the people it brings
 *  (app/services/sharing.py). */
export function EventShareMenu({ eventId, title, url, onShared, className, iconClassName }: {
  eventId: string; title: string; url: string;
  onShared?: (channel: ShareChannel) => void;
  className?: string; iconClassName?: string;
}) {
  const { token } = useAuthStore();
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const [waLink, setWaLink] = useState<string | null>(null);

  // Fetch the WhatsApp link as the menu opens, so tapping it can open WhatsApp straight away
  // (a link opened after waiting on the network is blocked as a pop-up on phones).
  useEffect(() => {
    if (!open || !token || waLink) return;
    shareApi.link(token, eventId, "whatsapp").then((r) => setWaLink(r.url)).catch(() => {});
  }, [open, token, eventId, waLink]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);

  async function linkFor(channel: ShareChannel): Promise<string> {
    if (!token) return url;
    try { return (await shareApi.link(token, eventId, channel)).url; } catch { return url; }
  }

  const text = `Check out ${title} on Turnup!`;

  async function share(channel: ShareChannel) {
    setOpen(false);
    if (channel === "whatsapp") {
      const wa = `https://wa.me/?text=${encodeURIComponent(`${text} ${waLink ?? url}`)}`;
      window.open(wa, "_blank", "noopener");
    } else if (channel === "native") {
      const link = await linkFor("native");
      try { await navigator.share({ title, text, url: link }); } catch { return; /* cancelled */ }
    } else {
      copyToClipboard(await linkFor("copy_link"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
    onShared?.(channel);
  }

  const canNative = typeof navigator !== "undefined" && !!navigator.share;
  const item = "w-full flex items-center gap-2 px-3 py-2 text-xs font-bold text-text hover:bg-bg-elevated text-left";

  return (
    <div className="relative" ref={box}>
      <button onClick={() => setOpen((v) => !v)} aria-label="Share this event" aria-expanded={open}
        className={cn("p-2 rounded border border-border-subtle hover:bg-bg-elevated hover:border-border transition-all duration-100", className)}>
        {copied
          ? <Check size={18} className={cn("text-success", iconClassName)} aria-hidden />
          : <Share2 size={18} className={cn(iconClassName)} aria-hidden />}
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full mt-1 z-30 min-w-[170px] bg-bg-card border-2 border-border rounded shadow-brutal-sm py-1">
          <button role="menuitem" className={item} onClick={() => share("whatsapp")}>
            <MessageCircle size={14} className="text-success" aria-hidden /> WhatsApp
          </button>
          {canNative && (
            <button role="menuitem" className={item} onClick={() => share("native")}>
              <Share2 size={14} aria-hidden /> More options…
            </button>
          )}
          <button role="menuitem" className={item} onClick={() => share("copy_link")}>
            <Copy size={14} aria-hidden /> Copy link
          </button>
        </div>
      )}
    </div>
  );
}

/** Records an open when the page was reached through someone's share link (?ref=CODE). */
export function useShareRef() {
  const { token, hasHydrated } = useAuthStore();
  const done = useRef(false);
  useEffect(() => {
    if (!hasHydrated || done.current || typeof window === "undefined") return;
    const code = new URLSearchParams(window.location.search).get("ref");
    if (!code || !/^[A-Za-z0-9]{4,12}$/.test(code)) return;
    done.current = true;
    shareApi.open(code, token ?? undefined).catch(() => { /* best effort */ });
  }, [hasHydrated, token]);
}
