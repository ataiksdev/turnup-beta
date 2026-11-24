"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Capacitor } from "@capacitor/core";
import { X } from "lucide-react";

const KEY = "turnup-storage-notice";

/** A one-time note about what Turnup keeps on the device. There's nothing to opt in or out
 *  of: only storage Turnup needs to work (sign-in, theme, offline tickets), no tracking. Not
 *  shown in the Android app, where that storage is part of the installed app. */
export function CookieNotice() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (Capacitor.isNativePlatform()) return;
    try {
      if (!localStorage.getItem(KEY)) setShow(true);
    } catch { /* storage blocked: nothing is being stored either */ }
  }, []);

  if (!show) return null;

  const dismiss = () => {
    setShow(false);
    try { localStorage.setItem(KEY, "1"); } catch { /* storage blocked */ }
  };

  return (
    <div role="region" aria-label="Storage notice"
      className="fixed inset-x-0 bottom-20 z-40 px-4 pointer-events-none">
      <div className="pointer-events-auto max-w-2xl mx-auto flex items-start gap-3 p-3 rounded border-2 border-border bg-bg-card shadow-brutal-sm text-xs text-text-secondary">
        <p className="flex-1">
          Turnup keeps your sign-in, theme and offline tickets on this device so the app works. No ads, no
          tracking cookies.{" "}
          <Link href="/privacy#storage" className="font-bold text-primary hover:underline">Privacy Policy</Link>
        </p>
        <button onClick={dismiss} className="shrink-0 font-bold text-text hover:text-primary" aria-label="Dismiss storage notice">
          <X size={16} aria-hidden />
        </button>
      </div>
    </div>
  );
}
