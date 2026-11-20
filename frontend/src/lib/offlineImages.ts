"use client";
import { useEffect, useState } from "react";
import { useOffline } from "@/lib/network";

/** Cover photos of the signed-in user's ticketed and saved events, kept for offline use. Uses
 *  the browser's Cache Storage (no service worker needed); only photos the server allows the
 *  app to read (CORS) can be kept, others show the usual placeholder offline. */
const CACHE = "turnup-offline-images";
const hasCaches = () => typeof window !== "undefined" && "caches" in window;

/** Keep exactly these photos: download the missing ones, delete the rest. */
export async function syncOfflineImages(urls: string[]): Promise<void> {
  if (!hasCaches()) return;
  const wanted = new Set(urls.filter((u) => /^https?:\/\//.test(u)));
  const cache = await caches.open(CACHE);
  const have = new Set((await cache.keys()).map((r) => r.url));
  await Promise.all([...have].filter((u) => !wanted.has(u)).map((u) => cache.delete(u)));
  for (const url of wanted) {
    if (have.has(url)) continue;
    try {
      const res = await fetch(url, { mode: "cors", credentials: "omit" });
      if (res.ok && (res.headers.get("content-type") ?? "").startsWith("image/")) await cache.put(url, res);
    } catch { /* no CORS or no network: this photo just isn't kept */ }
  }
}

export async function clearOfflineImages(): Promise<void> {
  if (hasCaches()) await caches.delete(CACHE).catch(() => false);
}

/** The photo's normal address while online; offline, the kept copy (or the original address,
 *  which then fails as before and the caller's placeholder shows). */
export function useOfflineImage(src: string | null | undefined): string | null | undefined {
  const offline = useOffline();
  const [local, setLocal] = useState<string | null>(null);
  useEffect(() => {
    if (!offline || !src || !hasCaches()) { setLocal(null); return; }
    let url: string | null = null;
    let cancelled = false;
    caches.open(CACHE).then((c) => c.match(src)).then(async (res) => {
      if (!res || cancelled) return;
      url = URL.createObjectURL(await res.blob());
      if (!cancelled) setLocal(url);
    }).catch(() => {});
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [offline, src]);
  return local ?? src;
}
