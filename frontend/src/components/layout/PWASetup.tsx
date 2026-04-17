"use client";
import { useEffect, useState } from "react";
import { Download, Share, X } from "lucide-react";

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export function PWASetup() {
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [showIOSHint, setShowIOSHint] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Register service worker
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
    }

    // Skip if already dismissed this session or running standalone
    if (
      sessionStorage.getItem("pwa-dismissed") ||
      window.matchMedia("(display-mode: standalone)").matches ||
      (navigator as { standalone?: boolean }).standalone
    ) {
      return;
    }

    const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
    const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);

    if (isIOS && isSafari) {
      // iOS Safari: show manual add-to-homescreen hint after 5 s
      const t = setTimeout(() => setShowIOSHint(true), 5000);
      return () => clearTimeout(t);
    }

    const handler = (e: Event) => {
      e.preventDefault();
      setInstallPrompt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  const dismiss = () => {
    setDismissed(true);
    setInstallPrompt(null);
    setShowIOSHint(false);
    sessionStorage.setItem("pwa-dismissed", "1");
  };

  const handleInstall = async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    const { outcome } = await installPrompt.userChoice;
    if (outcome === "accepted") dismiss();
  };

  if (dismissed) return null;

  // Android / Chrome install banner
  if (installPrompt) {
    return (
      <div
        role="dialog"
        aria-label="Install Turnup app"
        className="fixed bottom-24 inset-x-4 z-50 bg-bg-card border border-border rounded-2xl p-4 shadow-card animate-slide-up"
      >
        <button onClick={dismiss} aria-label="Dismiss install prompt"
          className="absolute top-3 right-3 p-1 rounded-lg hover:bg-bg-elevated text-text-muted">
          <X size={16} />
        </button>
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-primary/15 flex items-center justify-center shrink-0">
            <span className="text-2xl">🎉</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-bold text-text text-sm">Add Turnup to Home Screen</p>
            <p className="text-xs text-text-muted mt-0.5">Get the full app experience</p>
          </div>
        </div>
        <button onClick={handleInstall}
          className="mt-3 w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-primary text-white font-semibold text-sm">
          <Download size={16} /> Install App
        </button>
      </div>
    );
  }

  // iOS Safari hint
  if (showIOSHint) {
    return (
      <div
        role="dialog"
        aria-label="Add Turnup to Home Screen instructions"
        className="fixed bottom-24 inset-x-4 z-50 bg-bg-card border border-border rounded-2xl p-4 shadow-card animate-slide-up"
      >
        <button onClick={dismiss} aria-label="Dismiss"
          className="absolute top-3 right-3 p-1 rounded-lg hover:bg-bg-elevated text-text-muted">
          <X size={16} />
        </button>
        <p className="font-bold text-text text-sm mb-2">Install on iPhone</p>
        <p className="text-xs text-text-secondary leading-relaxed">
          Tap <Share size={12} className="inline -mt-0.5 text-info" /> <strong>Share</strong> at the
          bottom of Safari, then <strong>"Add to Home Screen"</strong> to install Turnup.
        </p>
      </div>
    );
  }

  return null;
}
