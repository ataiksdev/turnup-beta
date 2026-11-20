"use client";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { RefreshCw, WifiOff } from "lucide-react";
import { useOffline } from "@/lib/network";

/** Shown across the app while Turnup can't be reached. Screens keep whatever they already
 *  loaded; Retry (and coming back online) reloads it. While the phone claims to be online
 *  but the server is unreachable, it also retries on its own every 20 s. */
export function OfflineBanner() {
  const offline = useOffline();
  const pathname = usePathname() ?? "";
  const qc = useQueryClient();
  const [retrying, setRetrying] = useState(false);

  const retry = async () => {
    setRetrying(true);
    try { await qc.refetchQueries({ type: "active" }); } finally { setRetrying(false); }
  };

  useEffect(() => {
    if (!offline || !navigator.onLine) return; // the browser's 'online' event refetches by itself
    const t = setInterval(() => { qc.refetchQueries({ type: "active" }); }, 20_000);
    return () => clearInterval(t);
  }, [offline, qc]);

  if (!offline) return null;
  // These screens say they're offline themselves, at the top, and a floating banner must
  // never cover a ticket's QR code at the door.
  if (pathname === "/" || /^\/(tickets|saved|events)(\/|$)/.test(pathname)) return null;
  return (
    <div role="status" aria-live="polite"
      className="fixed inset-x-3 z-[55] mx-auto max-w-md flex items-center gap-3 px-3 py-2.5 rounded-md border-2 border-border bg-bg-elevated shadow-brutal animate-slide-up"
      style={{ bottom: "calc(5.75rem + env(safe-area-inset-bottom))" }}>
      <WifiOff size={18} className="text-text-muted shrink-0" aria-hidden />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-bold text-text leading-tight">You&apos;re offline</p>
        <p className="text-xs text-text-muted leading-tight mt-0.5">Showing what&apos;s already loaded.</p>
      </div>
      <button onClick={retry} disabled={retrying}
        className="btn shrink-0 inline-flex items-center gap-1.5 h-8 px-3 rounded border-2 border-border bg-bg-card text-xs font-bold text-text disabled:opacity-60">
        <RefreshCw size={13} className={retrying ? "animate-spin" : ""} aria-hidden /> Retry
      </button>
    </div>
  );
}
