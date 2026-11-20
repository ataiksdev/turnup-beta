import { useSyncExternalStore } from "react";

/** Fired after buying or saving, so the offline copy (OfflineSync) refreshes. */
export const OFFLINE_SYNC_EVENT = "turnup:offline-sync";
export function requestOfflineSync() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(OFFLINE_SYNC_EVENT));
}

/** The message an API call fails with when it can't reach the server at all. */
export const OFFLINE_MESSAGE = "You're offline. Check your connection and try again.";

// Offline = the phone says it has no connection, OR it says it has one but our last API call
// couldn't reach the server (Wi-Fi with no internet, mobile data off for the app, server down).
// request() in lib/api.ts reports every call's outcome here.
let serverReachable = true;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

export function reportReachable(ok: boolean) {
  if (serverReachable === ok) return;
  serverReachable = ok;
  notify();
}

function subscribe(listener: () => void) {
  if (typeof window === "undefined") return () => {};
  listeners.add(listener);
  window.addEventListener("online", listener);
  window.addEventListener("offline", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("online", listener);
    window.removeEventListener("offline", listener);
  };
}

const isOffline = () => (typeof navigator !== "undefined" && !navigator.onLine) || !serverReachable;

/** True while the app can't reach Turnup. False during server rendering. */
export function useOffline(): boolean {
  return useSyncExternalStore(subscribe, isOffline, () => false);
}
