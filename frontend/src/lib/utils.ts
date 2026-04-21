import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { format, formatDistanceToNow, isToday, isTomorrow } from "date-fns";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
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

export function formatPrice(
  isFree: boolean,
  priceMin?: number | null,
  priceMax?: number | null,
  currency = "NGN",
): string {
  if (isFree) return "Free";
  const sym = currency === "USD" ? "$" : currency === "EUR" ? "€" : currency === "GBP" ? "£" : `${currency} `;
  if (priceMin && priceMax && priceMin !== priceMax) {
    return `${sym}${priceMin}–${sym}${priceMax}`;
  }
  return `${sym}${priceMin ?? priceMax ?? 0}`;
}

export function formatCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function timeAgo(dateStr: string): string {
  return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
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
