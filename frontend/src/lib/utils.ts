import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { format, formatDistanceToNow, isToday, isTomorrow } from "date-fns";

/**
 * Returns `url` only if it is an absolute http(s) URL, otherwise undefined. Use for every
 * href built from user-supplied data: React 18 renders `javascript:` hrefs as-is, so an
 * unchecked profile website or meeting link is a click-to-run XSS. The backend validates
 * new input too; this also covers anything already stored before that validation existed.
 */
export function safeHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url.trim());
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function copyToClipboard(text: string): void {
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).catch(() => _fallbackCopy(text));
  } else {
    _fallbackCopy(text);
  }
}

function _fallbackCopy(text: string): void {
  const el = document.createElement("textarea");
  el.value = text;
  el.setAttribute("readonly", "");
  el.style.cssText = "position:fixed;top:-9999px;left:-9999px;opacity:0";
  document.body.appendChild(el);
  el.select();
  el.setSelectionRange(0, el.value.length);
  document.execCommand("copy");
  document.body.removeChild(el);
}

export function formatEventDate(dateStr: string): string {
  const date = new Date(dateStr);
  if (isToday(date)) return `Today · ${format(date, "h:mm a")}`;
  if (isTomorrow(date)) return `Tomorrow · ${format(date, "h:mm a")}`;
  return format(date, "EEE, MMM d · h:mm a");
}

export function formatEventDateShort(dateStr: string): string {
  const date = new Date(dateStr);
  if (isToday(date)) return "Today";
  if (isTomorrow(date)) return "Tomorrow";
  return format(date, "MMM d");
}

const SYMBOLS: Record<string, string> = { NGN: "₦", USD: "$", EUR: "€", GBP: "£" };

/** "₦5,000", "₦1,250.50". */
export function formatMoney(amount: number, currency = "NGN"): string {
  const sym = SYMBOLS[currency] ?? `${currency} `;
  return `${sym}${Number(amount).toLocaleString("en-NG", { maximumFractionDigits: 2 })}`;
}

export function formatPrice(
  isFree: boolean,
  priceMin?: number | null,
  priceMax?: number | null,
  currency = "NGN",
): string {
  if (isFree) return "Free";
  if (priceMin && priceMax && priceMin !== priceMax) {
    return `${formatMoney(priceMin, currency)} – ${formatMoney(priceMax, currency)}`;
  }
  return formatMoney(priceMin ?? priceMax ?? 0, currency);
}

export function formatCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function timeAgo(dateStr: string): string {
  return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
}

/** Returns the display name for a user — display_name takes priority over full_name. */
export function displayName(user: { display_name?: string | null; full_name?: string | null; username?: string }): string {
  return user.display_name?.trim() || user.full_name?.trim() || user.username || "";
}

export function getInitials(name: string): string {
  return name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

export function parseTags(tags?: string | null): string[] {
  if (!tags) return [];
  return tags.split(",").map((t) => t.trim()).filter(Boolean);
}

export function parsePreferences(prefs?: string | null): string[] {
  if (!prefs) return [];
  return prefs.split(",").map((t) => t.trim()).filter(Boolean);
}
