/**
 * Activity tracking (docs/recommendations-spec.md).
 *
 * track(name, …) queues an event; the queue is mirrored to localStorage (so nothing is lost
 * offline or when the app is killed) and sent to POST /api/track in batches: every 5 seconds
 * on Wi-Fi, every 30 on mobile data or Data Saver, straight away when the queue fills, and
 * when the app goes to the background. Purchases, RSVPs, saves and check-ins are recorded
 * by the server itself, not here.
 */
import { Capacitor } from "@capacitor/core";
import { randomId } from "@/lib/utils";

export type TrackName =
  | "session_started"
  | "feed_impression" | "event_clicked" | "search_executed"
  | "event_viewed" | "event_dwell_ended" | "event_shared"
  | "ticket_drawer_opened" | "ticket_tier_selected" | "checkout_abandoned"
  | "notification_interacted";

export interface TrackData {
  event_id?: string;
  surface?: string;
  position?: number;
  rec_request_id?: string | null;
  is_promoted?: boolean;
  props?: Record<string, unknown>;
}

interface Queued extends TrackData { id: string; name: TrackName; ts: string }

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "0.1.0";
const ANON_KEY = "turnup-anon-id";
const SESSION_KEY = "turnup-session";
const QUEUE_KEY = "turnup-track-queue";
const CLICK_KEY = "turnup-last-click";
const SESSION_IDLE_MS = 30 * 60 * 1000;
const MAX_QUEUE = 500;          // keep at most this many unsent events on the phone
const MAX_BATCH = 50;           // the server's limit per request

const isBrowser = () => typeof window !== "undefined";

function store(): Storage | null {
  try { return isBrowser() ? window.localStorage : null; } catch { return null; }
}

// ── Identity ───────────────────────────────────────────────────────────────────

let memoryAnonId: string | null = null;

/** A random id for this device, kept until the app's storage is cleared. */
export function getAnonymousId(): string {
  const s = store();
  const existing = s?.getItem(ANON_KEY) ?? memoryAnonId;
  if (existing) return existing;
  const id = randomId();
  memoryAnonId = id;
  s?.setItem(ANON_KEY, id);
  return id;
}

/** A session ends after 30 minutes without activity. Starting one is itself tracked. */
function getSessionId(): string {
  const s = store();
  const now = Date.now();
  let session: { id: string; last: number } | null = null;
  try { session = JSON.parse(s?.getItem(SESSION_KEY) ?? "null"); } catch { /* corrupt: start over */ }
  const fresh = !session || now - session.last > SESSION_IDLE_MS;
  if (fresh) session = { id: randomId(), last: now };
  session!.last = now;
  s?.setItem(SESSION_KEY, JSON.stringify(session));
  if (fresh) enqueue("session_started", { props: sessionProps() });
  return session!.id;
}

function sessionProps(): Record<string, unknown> {
  const url = isBrowser() ? new URL(window.location.href) : null;
  const d = new Date();
  return {
    entry_point: url?.searchParams.get("utm_source") ? "campaign"
      : document.referrer && !document.referrer.startsWith(window.location.origin) ? "link" : "direct",
    local_hour: d.getHours(), day_of_week: d.getDay(),
  };
}

function platform(): "web" | "android" | "ios" {
  try {
    const p = Capacitor.getPlatform();
    return p === "android" || p === "ios" ? p : "web";
  } catch { return "web"; }
}

// Referrer and campaign of the visit that started this page load (sent with every batch).
let attribution: { referrer?: string; utm_campaign?: string } | null = null;
function getAttribution() {
  if (attribution || !isBrowser()) return attribution ?? {};
  const url = new URL(window.location.href);
  const ref = document.referrer && !document.referrer.startsWith(window.location.origin)
    ? document.referrer.slice(0, 300) : undefined;
  attribution = { referrer: ref, utm_campaign: url.searchParams.get("utm_campaign")?.slice(0, 100) ?? undefined };
  return attribution;
}

// ── Who's signed in, and their location choice ────────────────────────────────

interface AuthSnapshot { token: string | null; city?: string | null; profilingConsent?: boolean }
let auth: AuthSnapshot = { token: null };

/** Called by TrackingProvider whenever the signed-in user changes. */
export function setTrackingAuth(next: AuthSnapshot) {
  const signedIn = !auth.token && !!next.token;
  auth = next;
  if (signedIn) {
    // This device's signed-out browsing now belongs to the account.
    fetch(`${BASE}/api/track/identify`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${next.token}` },
      body: JSON.stringify({ anonymous_id: getAnonymousId() }),
    }).catch(() => {});
  }
  if (next.profilingConsent) refreshPosition();
}

// Coordinates are only ever read when location permission was already granted (we never
// ask for it here) and the user opted in to profiling; the server drops them otherwise.
let position: { lat: number; lon: number; at: number } | null = null;
function refreshPosition() {
  if (!isBrowser() || !navigator.geolocation || !navigator.permissions) return;
  if (position && Date.now() - position.at < 10 * 60 * 1000) return;
  navigator.permissions.query({ name: "geolocation" as PermissionName }).then((p) => {
    if (p.state !== "granted") return;
    navigator.geolocation.getCurrentPosition(
      (pos) => { position = { lat: pos.coords.latitude, lon: pos.coords.longitude, at: Date.now() }; },
      () => {}, { maximumAge: 10 * 60 * 1000, timeout: 10000 },
    );
  }).catch(() => {});
}

// ── Queue ──────────────────────────────────────────────────────────────────────

let queue: Queued[] | null = null;

function loadQueue(): Queued[] {
  if (queue) return queue;
  try { queue = JSON.parse(store()?.getItem(QUEUE_KEY) ?? "[]"); } catch { queue = []; }
  if (!Array.isArray(queue)) queue = [];
  return queue!;
}

function saveQueue() {
  try { store()?.setItem(QUEUE_KEY, JSON.stringify(loadQueue().slice(-MAX_QUEUE))); } catch { /* full */ }
}

function enqueue(name: TrackName, data: TrackData = {}) {
  const q = loadQueue();
  q.push({ id: randomId(), name, ts: new Date().toISOString(), ...data });
  if (q.length > MAX_QUEUE) q.splice(0, q.length - MAX_QUEUE);
  saveQueue();
}

/** Record something the person did. Safe to call anywhere; never throws. */
export function track(name: TrackName, data: TrackData = {}) {
  if (!isBrowser()) return;
  try {
    getSessionId(); // may queue session_started first
    enqueue(name, data);
    if (loadQueue().length >= (onMobileData() ? MAX_BATCH : 20)) void flush();
    else schedule();
  } catch { /* tracking must never break the app */ }
}

// Mobile data costs people money in Nigeria: send less often there (and on Data Saver).
function onMobileData(): boolean {
  const c = (navigator as Navigator & { connection?: { type?: string; effectiveType?: string; saveData?: boolean } }).connection;
  if (!c) return false;
  return c.saveData === true || c.type === "cellular" || c.effectiveType === "2g" || c.effectiveType === "slow-2g"
    || c.effectiveType === "3g";
}

let timer: ReturnType<typeof setTimeout> | null = null;
function schedule() {
  if (timer) return;
  timer = setTimeout(() => { timer = null; void flush(); }, onMobileData() ? 30000 : 5000);
}

let sending = false;
export async function flush(): Promise<void> {
  if (!isBrowser() || sending) return;
  const q = loadQueue();
  if (!q.length || !navigator.onLine) return;
  sending = true;
  const batch = q.slice(0, MAX_BATCH);
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
    const geo = auth.city || position ? {
      city: auth.city ?? undefined,
      ...(auth.profilingConsent && position ? { lat: position.lat, lon: position.lon } : {}),
    } : undefined;
    const res = await fetch(`${BASE}/api/track`, {
      method: "POST", headers, keepalive: true,
      body: JSON.stringify({
        anonymous_id: getAnonymousId(), session_id: getSessionIdQuiet(), platform: platform(),
        app_version: APP_VERSION, ...getAttribution(), geo, events: batch,
      }),
    });
    // Sent, or rejected for good (a bad batch would otherwise block the queue forever).
    // Kept for another try: rate limited, server errors.
    if (res.ok || (res.status >= 400 && res.status < 500 && res.status !== 429 && res.status !== 401)) {
      const sent = new Set(batch.map((e) => e.id));
      queue = loadQueue().filter((e) => !sent.has(e.id));
      saveQueue();
    }
  } catch { /* offline: try again later */ } finally {
    sending = false;
  }
  if (loadQueue().length) schedule();
}

function getSessionIdQuiet(): string | undefined {
  try { return JSON.parse(store()?.getItem(SESSION_KEY) ?? "null")?.id; } catch { return undefined; }
}

/** Wire up background/foreground and connectivity. Called once by TrackingProvider. */
export function startTracking(): () => void {
  if (!isBrowser()) return () => {};
  getSessionId();
  const onHide = () => { if (document.visibilityState === "hidden") void flush(); };
  const onOnline = () => void flush();
  document.addEventListener("visibilitychange", onHide);
  window.addEventListener("pagehide", onOnline);
  window.addEventListener("online", onOnline);
  void flush();
  return () => {
    document.removeEventListener("visibilitychange", onHide);
    window.removeEventListener("pagehide", onOnline);
    window.removeEventListener("online", onOnline);
  };
}

// ── Where a click came from ────────────────────────────────────────────────────

export interface ClickOrigin { event_id: string; surface: string; position?: number; rec_request_id?: string | null }

/** A card remembers it was tapped, so the event page can say where the view came from. */
export function rememberClick(origin: ClickOrigin) {
  try { sessionStorage.setItem(CLICK_KEY, JSON.stringify({ ...origin, at: Date.now() })); } catch { /* ignore */ }
}

export function takeClick(eventId: string): ClickOrigin | null {
  try {
    const raw = JSON.parse(sessionStorage.getItem(CLICK_KEY) ?? "null");
    sessionStorage.removeItem(CLICK_KEY);
    return raw && raw.event_id === eventId && Date.now() - raw.at < 60000 ? raw : null;
  } catch { return null; }
}
