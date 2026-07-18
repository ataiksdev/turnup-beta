"use client";
import { Check, Copy, Share2 } from "lucide-react";
import { useState } from "react";
import { cn, copyToClipboard } from "@/lib/utils";

interface ShareButtonProps {
  title: string;
  text?: string;
  url: string;
  className?: string;
  iconClassName?: string;
  size?: number;
}

export function ShareButton({ title, text, url, className, iconClassName, size = 18 }: ShareButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleShare = async () => {
    // Native share sheet (mobile Safari, Android Chrome)
    if (navigator.share) {
      try {
        await navigator.share({ title, text: text ?? title, url });
      } catch {
        // User cancelled — not an error
      }
      return;
    }
    // Clipboard fallback for desktop / plain-HTTP origins
    copyToClipboard(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleShare}
      aria-label="Share this event"
      className={cn(
        "p-2 rounded border border-border-subtle hover:bg-bg-elevated hover:border-border transition-all duration-100",
        className,
      )}
    >
      {copied
        ? <Check size={size} className={cn("text-success", iconClassName)} aria-hidden />
        : <Share2 size={size} className={cn(iconClassName)} aria-hidden />}
    </button>
  );
}
