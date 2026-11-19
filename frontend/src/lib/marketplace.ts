/**
 * Venue marketplace and Turnup+ API (docs/venues-spec.md). Money is in kobo everywhere.
 */
import { ApiError, request } from "@/lib/api";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

// ── Types ──────────────────────────────────────────────────────────────────────

export type VenueType = "hall" | "lounge" | "hotel_studio" | "outdoor";
export type Preset = "flexible" | "moderate" | "strict";
export type VenueRole = "owner" | "manager" | "viewer";

export interface Area { id: string; state: string; name: string; slug: string; kind: string;
  latitude: number | null; longitude: number | null }
export interface StateOption { id: string; label: string }

export interface Price { display: "from" | "range" | "on_request"; from_kobo?: number; to_kobo?: number }

export interface VenueCard {
  id: string; slug: string; name: string; type: VenueType; state: string; area: string | null;
  area_id: string | null; cover_image: string | null; capacity: number; price: Price;
  is_verified: boolean; is_pro: boolean; featured: "state" | "area" | null; followers_count: number;
  rating_organizers: number | null; reviews_organizers_count: number;
  rating_guests: number | null; reviews_guests_count: number;
  latitude: number | null; longitude: number | null; distance_m: number | null;
}

export interface Space {
  id: string; name: string; description: string | null; capacity_seated: number | null;
  capacity_standing: number | null; setting: string; price_from_kobo: number | null;
  price_to_kobo: number | null; price_unit: "per_day" | "per_hour" | "per_event";
  min_hours: number | null; is_active: boolean; sort_order: number;
}

export interface Media { id: string; kind: "photo" | "video"; url: string; poster_url: string | null;
  duration_s: number | null; caption: string | null; space_id: string | null; sort_order: number; hidden: boolean }

export interface Deal { id: string; title: string; description: string | null; kind: string;
  valid_from?: string | null; valid_to: string | null; max_per_member?: number; is_active?: boolean;
  redemptions?: number }

export interface VenueDetail extends VenueCard {
  description: string | null; address: string; amenities: string[]; rules: string | null;
  status: string; accepting_enquiries: boolean; deposits_enabled: boolean; refund_preset: Preset;
  refund_policy: string; deposit_type: "percent" | "fixed"; deposit_value: number; balance_due_days: number;
  spaces: Space[]; media: Media[]; is_following: boolean; cancellations_last_year: number;
  strikes_last_year: number; deals: Deal[]; viewer_is_plus: boolean;
}

export interface Quote {
  id: string; space_id: string; starts_at: string; ends_at: string; total_kobo: number;
  deposit_kobo: number; balance_kobo: number; balance_due_days: number; refund_preset: Preset;
  refund_policy: string; inclusions: string | null; valid_until: string; status: string; created_at: string;
}

export interface Message { id: string; sender_side: "organizer" | "venue" | "system"; sender_id: string | null;
  body: string; quote: Quote | null; flagged_contact: boolean; created_at: string }

export interface UserBrief { id: string; username: string; display_name: string | null; avatar_url: string | null;
  email?: string | null; phone?: string | null }

export interface Enquiry {
  id: string; status: string; starts_at: string; ends_at: string; guest_count: number;
  event_type: string | null; budget_kobo: number | null; last_message_at: string; created_at: string;
  unread: number; venue: { id: string; slug: string; name: string; cover_image: string | null;
    deposits_enabled: boolean; status: string };
  space: Space | null; organizer: UserBrief | null;
  organizer_trusted: { completed_bookings: number; trusted: boolean }; booking_id: string | null;
  messages?: Message[];
}

export interface RefundRequest {
  id: string; booking_id: string; reason: string; amount_kobo: number; funded_kobo: number;
  refunded_kobo: number; due_at: string; status: string; paused_at: string | null;
  suspended_at: string | null; referred_at: string | null; settled_by_organizer: boolean;
  settled_by_venue: boolean; created_at: string;
}

export interface Dispute { id: string; side: string; reason: string; description: string; status: string;
  resolution: string | null; refund_kobo: number | null; decision_note: string | null; created_at: string;
  resolved_at: string | null }

export interface Booking {
  id: string; status: string; enquiry_id: string; quote_id: string; starts_at: string; ends_at: string;
  total_kobo: number; deposit_kobo: number; paid_kobo: number; refunded_kobo: number; balance_kobo: number;
  balance_due_at: string; refund_preset: Preset; refund_policy: string; cancelled_at: string | null;
  cancel_reason: string | null; completed_at: string | null; event_id: string | null; created_at: string;
  venue: { id: string; slug: string; name: string; cover_image: string | null; status: string;
    address: string | null; phone: string | null; email: string | null };
  space: Space; organizer: UserBrief | null; refund_requests: RefundRequest[]; disputes: Dispute[];
  commission_kobo?: number; commission_percent?: number;
}

export interface CancelPreview { refund_percent: number; refund_kobo: number; paid_kobo: number;
  funded_by: "venue"; strike?: boolean; status?: string }

export interface PayLink { reference: string; authorization_url: string; amount_kobo?: number; booking_id?: string }

export interface ChecklistItem { id: string; label: string; done: boolean }

export interface PortalVenue extends VenueCard {
  my_role: VenueRole; status: string; pause_reason: string | null; verification_status: string;
  verification_note: string | null; deposits_enabled: boolean; description: string | null; address: string;
  area_other: string | null; amenities: string[]; rules: string | null; phone: string | null; email: string | null;
  price_display: Price["display"]; refund_preset: Preset; refund_policy: string;
  deposit_type: "percent" | "fixed"; deposit_value: number; balance_due_days: number;
  legal_name: string | null; cac_number: string | null; registered_address: string | null;
  bank: { bank_name: string | null; account_last4: string | null; account_name: string | null;
    name_match: boolean | null; ready: boolean };
  spaces: Space[]; media: Media[]; limits: { photos: number; videos: number; team_seats: number };
  documents: { id: string; kind: string; status: string; original_filename: string | null;
    rejection_reason: string | null; created_at: string }[];
  visit: { status: string; scheduled_for: string | null } | null;
  pro: { active: boolean; until: string | null; status: string | null; plan_code: string | null };
  balance_kobo: number; late_refunds: number; strikes_last_year: number; checklist: ChecklistItem[];
}

export interface MyVenue extends VenueCard { my_role: VenueRole; status: string; verification_status: string }

export interface Plan { code: string; product?: string; name: string; amount_kobo: number; interval: "monthly" | "annually" }
export interface Perk { id: string; title: string; body: string }

export interface PlusMe { is_plus: boolean; until: string | null; status: string | null; plan_code: string | null;
  renews: boolean; show_plus_badge: boolean; wrapped_opt_in: boolean }

export interface ClaimedDeal { code: string; claimed_at: string; redeemed_at: string | null;
  deal: Deal; where: { type: "venue" | "event"; name: string; slug?: string; id?: string } | null }

export interface Wrapped {
  year: number; events_attended: number; cities_count: number; venues_count: number; full: boolean;
  top_venues?: { name: string; visits: number }[]; top_organizers?: { name: string; events: number }[];
  top_cities?: { name: string; events: number }[]; busiest_month?: string | null;
  went_with?: { username: string; name: string; events: number }[];
}

export interface WeekendPicks { weekend_start: string; weekend_end: string; city: string | null;
  events: { id: string; slug: string; title: string; cover_image: string | null; start_date: string;
    venue_name: string; city: string; is_free: boolean; price_min: number | null; members_only: boolean;
    because: string }[] }

export interface VenueReview { id: string; kind: "organizer" | "guest"; rating: number; body: string | null;
  venue_reply: string | null; venue_reply_at?: string | null; is_hidden?: boolean; created_at: string;
  author: UserBrief & { is_plus?: boolean } }

// ── Helpers ────────────────────────────────────────────────────────────────────

export function naira(kobo: number | null | undefined): string {
  const n = (kobo ?? 0) / 100;
  return `₦${n.toLocaleString("en-NG", { maximumFractionDigits: n % 1 ? 2 : 0 })}`;
}

export function priceLabel(p: Price): string {
  if (p.display === "on_request" || p.from_kobo == null) return "Price on request";
  if (p.display === "range" && p.to_kobo && p.to_kobo !== p.from_kobo) return `${naira(p.from_kobo)} – ${naira(p.to_kobo)}`;
  return `From ${naira(p.from_kobo)}`;
}

export const VENUE_TYPES: { id: VenueType; label: string }[] = [
  { id: "hall", label: "Event halls & centres" },
  { id: "lounge", label: "Lounges, clubs & bars" },
  { id: "hotel_studio", label: "Hotels & studios" },
  { id: "outdoor", label: "Outdoor & beach" },
];

export const BOOKING_STATUS: Record<string, string> = {
  pending_payment: "Awaiting deposit", confirmed: "Confirmed", fully_paid: "Paid in full",
  cancelled_by_organizer: "Cancelled by you", cancelled_by_venue: "Cancelled by the venue",
  cancelled_unpaid_balance: "Cancelled: balance unpaid", completed: "Completed", disputed: "In dispute",
  expired: "Expired",
};

export const REFUND_STATUS: Record<string, string> = {
  awaiting_venue: "Waiting for the venue to pay it in", funded: "Paid in by the venue, sending to you",
  refunded: "Refunded", overdue: "Overdue: venue paused, next payments go to you",
  suspended: "Overdue: venue suspended", referred: "Referred to you (claim pack available)",
  settled_directly: "Settled directly",
};

/** Paystack sends the payer back here; the page verifies and forwards to `next`. */
export function paymentCallback(next: string): string {
  if (typeof window === "undefined") return "";
  return `${window.location.origin}/payments/callback?next=${encodeURIComponent(next)}`;
}

export function goToPayment(link: PayLink) {
  window.location.href = link.authorization_url;
}

async function upload<T>(token: string, path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, { method: "POST", body: form, headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof err.detail === "string" ? err.detail
      : res.status === 413 ? "That file is too large." : "Upload failed. Please try again.");
  }
  return res.json();
}

const json = (body: unknown) => ({ body: JSON.stringify(body) });
const qs = (params: Record<string, string | number | boolean | undefined | null>) => {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
};

// ── Public ─────────────────────────────────────────────────────────────────────

export interface VenueSearch {
  state?: string; area_ids?: string; lat?: number; lng?: number; radius_km?: number; type?: string;
  min_capacity?: number; date?: string; max_price_kobo?: number; amenities?: string; verified_only?: boolean;
  q?: string; sort?: string; limit?: number; offset?: number;
}

export const venuesApi = {
  states: () => request<StateOption[]>("/places/states"),
  areas: (state: string) => request<Area[]>(`/places/areas${qs({ state })}`),
  search: (p: VenueSearch) => request<{ total: number; items: VenueCard[] }>(`/venues${qs({ ...p })}`),
  featured: (p: VenueSearch) => request<VenueCard[]>(`/venues/featured${qs({ ...p })}`),
  get: (slug: string, token?: string | null) => request<VenueDetail>(`/venues/${encodeURIComponent(slug)}`, {}, token ?? undefined),
  availability: (slug: string, start: string, end: string) =>
    request<{ busy: { space_id: string | null; starts_at: string; ends_at: string }[] }>(
      `/venues/${encodeURIComponent(slug)}/availability${qs({ start, end })}`),
  reviews: (slug: string, kind?: "organizer" | "guest") =>
    request<VenueReview[]>(`/venues/${encodeURIComponent(slug)}/reviews${qs({ kind })}`),
  events: (slug: string) => request<{ id: string; slug: string; title: string; cover_image: string | null;
    start_date: string; is_free: boolean; price_min: number | null; hosted_by_venue: boolean; members_only: boolean }[]>(
      `/venues/${encodeURIComponent(slug)}/events`),
  follow: (token: string, slug: string) => request<{ following: boolean; followers_count: number }>(
    `/venues/${encodeURIComponent(slug)}/follow`, { method: "POST" }, token),
  unfollow: (token: string, slug: string) => request<{ following: boolean; followers_count: number }>(
    `/venues/${encodeURIComponent(slug)}/follow`, { method: "DELETE" }, token),
  following: (token: string) => request<VenueCard[]>("/me/following-venues", {}, token),
};

// ── Organizer side ─────────────────────────────────────────────────────────────

export const bookingsApi = {
  enquire: (token: string, slug: string, body: { space_id?: string | null; starts_at: string; ends_at: string;
    guest_count: number; event_type?: string; budget_kobo?: number | null; message: string }) =>
    request<Enquiry>(`/venues/${encodeURIComponent(slug)}/enquiries`, { method: "POST", ...json(body) }, token),
  enquiries: (token: string) => request<Enquiry[]>("/enquiries", {}, token),
  enquiry: (token: string, id: string) => request<Enquiry>(`/enquiries/${id}`, {}, token),
  message: (token: string, id: string, body: string) =>
    request<Enquiry>(`/enquiries/${id}/messages`, { method: "POST", ...json({ body }) }, token),
  report: (token: string, id: string, details: string, message_id?: string) =>
    request<{ ok: boolean }>(`/enquiries/${id}/report`, { method: "POST", ...json({ details, message_id }) }, token),
  acceptQuote: (token: string, quoteId: string, callback_url: string) =>
    request<PayLink>(`/quotes/${quoteId}/accept`, { method: "POST", ...json({ callback_url }) }, token),
  declineQuote: (token: string, quoteId: string) =>
    request<{ ok: boolean }>(`/quotes/${quoteId}/decline`, { method: "POST" }, token),
  verify: (token: string, reference: string) =>
    request<{ status: string }>(`/venue-payments/verify${qs({ reference })}`, { method: "POST" }, token),
  bookings: (token: string) => request<Booking[]>("/venue-bookings", {}, token),
  booking: (token: string, id: string) => request<Booking>(`/venue-bookings/${id}`, {}, token),
  pay: (token: string, id: string, amount_kobo: number | null, callback_url: string) =>
    request<PayLink>(`/venue-bookings/${id}/pay`, { method: "POST", ...json({ amount_kobo, callback_url }) }, token),
  cancel: (token: string, id: string, preview: boolean, reason?: string) =>
    request<CancelPreview>(`/venue-bookings/${id}/cancel`, { method: "POST", ...json({ preview, reason }) }, token),
  dispute: (token: string, id: string, body: { reason: string; description: string; evidence?: string[] }) =>
    request<{ id: string }>(`/venue-bookings/${id}/disputes`, { method: "POST", ...json(body) }, token),
  review: (token: string, id: string, rating: number, body?: string) =>
    request<{ id: string }>(`/venue-bookings/${id}/review`, { method: "POST", ...json({ rating, body }) }, token),
  settled: (token: string, rrId: string) =>
    request<RefundRequest>(`/refund-requests/${rrId}/settled`, { method: "POST" }, token),
  claimPackUrl: (rrId: string) => `${BASE}/api/refund-requests/${rrId}/claim-pack`,
  guestReview: (token: string, eventId: string, rating: number, body?: string) =>
    request<{ id: string }>(`/events/${eventId}/venue-review`, { method: "POST", ...json({ rating, body }) }, token),
};

/** Downloads an authenticated file (claim pack) and opens/saves it. */
export async function downloadWithAuth(token: string, url: string, filename: string) {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof err.detail === "string" ? err.detail : "Download failed.");
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}

// ── Venue portal ───────────────────────────────────────────────────────────────

const V = (id: string) => `/venue-portal/venues/${id}`;

export const portalApi = {
  myVenues: (token: string) => request<MyVenue[]>("/venue-portal/venues", {}, token),
  create: (token: string, body: Record<string, unknown>) =>
    request<PortalVenue>("/venue-portal/venues", { method: "POST", ...json(body) }, token),
  get: (token: string, id: string) => request<PortalVenue>(V(id), {}, token),
  update: (token: string, id: string, body: Record<string, unknown>) =>
    request<PortalVenue>(V(id), { method: "PATCH", ...json(body) }, token),
  close: (token: string, id: string) => request<void>(V(id), { method: "DELETE" }, token),
  addSpace: (token: string, id: string, body: Partial<Space>) =>
    request<Space>(`${V(id)}/spaces`, { method: "POST", ...json(body) }, token),
  updateSpace: (token: string, id: string, spaceId: string, body: Partial<Space>) =>
    request<Space>(`${V(id)}/spaces/${spaceId}`, { method: "PUT", ...json(body) }, token),
  deleteSpace: (token: string, id: string, spaceId: string) =>
    request<void>(`${V(id)}/spaces/${spaceId}`, { method: "DELETE" }, token),
  addMedia: (token: string, id: string, body: { kind: "photo" | "video"; url: string; poster_url?: string | null;
    duration_s?: number | null; caption?: string; space_id?: string | null }) =>
    request<Media[]>(`${V(id)}/media`, { method: "POST", ...json(body) }, token),
  reorderMedia: (token: string, id: string, ids: string[]) =>
    request<Media[]>(`${V(id)}/media/order`, { method: "PUT", ...json({ ids }) }, token),
  deleteMedia: (token: string, id: string, mediaId: string) =>
    request<Media[]>(`${V(id)}/media/${mediaId}`, { method: "DELETE" }, token),
  uploadVideo: (token: string, file: File) => {
    const f = new FormData(); f.append("file", file);
    return upload<{ url: string; poster_url: string | null; duration_s: number | null }>(token, "/uploads/video", f);
  },
  uploadDocument: (token: string, id: string, kind: string, file: File) => {
    const f = new FormData(); f.append("kind", kind); f.append("file", file);
    return upload<{ id: string }>(token, `${V(id)}/documents`, f);
  },
  deleteDocument: (token: string, id: string, docId: string) =>
    request<void>(`${V(id)}/documents/${docId}`, { method: "DELETE" }, token),
  banks: (token: string) => request<{ name: string; code: string }[]>("/venue-portal/banks", {}, token),
  setBank: (token: string, id: string, bank_code: string, account_number: string) =>
    request<PortalVenue>(`${V(id)}/bank`, { method: "PUT", ...json({ bank_code, account_number }) }, token),
  submit: (token: string, id: string) => request<PortalVenue>(`${V(id)}/submit`, { method: "POST" }, token),
  members: (token: string, id: string) => request<{ members: { user: UserBrief; role: VenueRole; created_at: string }[];
    invites: { id: string; email: string; role: VenueRole; expires_at: string }[]; seats: number }>(`${V(id)}/members`, {}, token),
  invite: (token: string, id: string, email: string, role: "manager" | "viewer") =>
    request<{ id: string; link: string | null }>(`${V(id)}/invites`, { method: "POST", ...json({ email, role }) }, token),
  revokeInvite: (token: string, id: string, inviteId: string) =>
    request<void>(`${V(id)}/invites/${inviteId}`, { method: "DELETE" }, token),
  acceptInvite: (token: string, inviteToken: string) =>
    request<{ venue_id: string }>(`/venue-portal/invites/accept${qs({ token: inviteToken })}`, { method: "POST" }, token),
  setRole: (token: string, id: string, userId: string, role: VenueRole) =>
    request<{ ok: boolean }>(`${V(id)}/members/${userId}`, { method: "PATCH", ...json({ role }) }, token),
  removeMember: (token: string, id: string, userId: string) =>
    request<void>(`${V(id)}/members/${userId}`, { method: "DELETE" }, token),
  calendar: (token: string, id: string, start: string, end: string) =>
    request<{ bookings: { id: string; space_id: string; starts_at: string; ends_at: string; status: string; organizer: UserBrief | null }[];
      blocks: { id: string; space_id: string | null; starts_at: string; ends_at: string; note: string | null }[] }>(
      `${V(id)}/calendar${qs({ start, end })}`, {}, token),
  addBlock: (token: string, id: string, body: { space_id?: string | null; starts_at: string; ends_at: string; note?: string }) =>
    request<{ id: string }>(`${V(id)}/blocks`, { method: "POST", ...json(body) }, token),
  deleteBlock: (token: string, id: string, blockId: string) =>
    request<void>(`${V(id)}/blocks/${blockId}`, { method: "DELETE" }, token),
  enquiries: (token: string, id: string) => request<Enquiry[]>(`${V(id)}/enquiries`, {}, token),
  enquiry: (token: string, id: string, eid: string) => request<Enquiry>(`${V(id)}/enquiries/${eid}`, {}, token),
  message: (token: string, id: string, eid: string, body: string) =>
    request<Enquiry>(`${V(id)}/enquiries/${eid}/messages`, { method: "POST", ...json({ body }) }, token),
  quote: (token: string, id: string, eid: string, body: { space_id: string; starts_at: string; ends_at: string;
    total_kobo: number; deposit_kobo?: number | null; balance_due_days?: number | null; inclusions?: string; valid_days?: number }) =>
    request<Enquiry>(`${V(id)}/enquiries/${eid}/quotes`, { method: "POST", ...json(body) }, token),
  decline: (token: string, id: string, eid: string, body: string) =>
    request<Enquiry>(`${V(id)}/enquiries/${eid}/decline`, { method: "POST", ...json({ body }) }, token),
  bookings: (token: string, id: string) => request<Booking[]>(`${V(id)}/bookings`, {}, token),
  booking: (token: string, id: string, bid: string) => request<Booking>(`${V(id)}/bookings/${bid}`, {}, token),
  cancelBooking: (token: string, id: string, bid: string, preview: boolean, reason?: string) =>
    request<CancelPreview>(`${V(id)}/bookings/${bid}/cancel`, { method: "POST", ...json({ preview, reason }) }, token),
  cancelUnpaid: (token: string, id: string, bid: string, preview: boolean) =>
    request<CancelPreview>(`${V(id)}/bookings/${bid}/cancel-unpaid`, { method: "POST", ...json({ preview }) }, token),
  dispute: (token: string, id: string, bid: string, body: { reason: string; description: string }) =>
    request<{ id: string }>(`${V(id)}/bookings/${bid}/disputes`, { method: "POST", ...json(body) }, token),
  refunds: (token: string, id: string) => request<RefundRequest[]>(`${V(id)}/refunds`, {}, token),
  fundRefund: (token: string, id: string, rrId: string, callback_url: string) =>
    request<PayLink>(`${V(id)}/refunds/${rrId}/fund`, { method: "POST", ...json({ callback_url }) }, token),
  settled: (token: string, id: string, rrId: string) =>
    request<RefundRequest>(`${V(id)}/refunds/${rrId}/settled`, { method: "POST" }, token),
  ledger: (token: string, id: string) => request<{ balance_kobo: number; entries: { id: string; kind: string;
    amount_kobo: number; note: string | null; created_at: string }[] }>(`${V(id)}/ledger`, {}, token),
  payLedger: (token: string, id: string, callback_url: string) =>
    request<PayLink>(`${V(id)}/ledger/pay`, { method: "POST", ...json({ callback_url }) }, token),
  reviews: (token: string, id: string) => request<VenueReview[]>(`${V(id)}/reviews`, {}, token),
  reply: (token: string, id: string, rid: string, body: string) =>
    request<{ ok: boolean }>(`${V(id)}/reviews/${rid}/reply`, { method: "PUT", ...json({ body }) }, token),
  deals: (token: string, id: string) => request<Deal[]>(`${V(id)}/deals`, {}, token),
  createDeal: (token: string, id: string, body: Partial<Deal>) =>
    request<Deal>(`${V(id)}/deals`, { method: "POST", ...json(body) }, token),
  updateDeal: (token: string, id: string, dealId: string, body: Partial<Deal>) =>
    request<Deal>(`${V(id)}/deals/${dealId}`, { method: "PUT", ...json(body) }, token),
  redeem: (token: string, id: string, code: string) =>
    request<{ ok: boolean; reason?: string; deal: string; member?: string }>(
      `${V(id)}/deals/redeem`, { method: "POST", ...json({ code }) }, token),
  plans: () => request<Plan[]>("/venue-portal/plans"),
  subscribePro: (token: string, id: string, plan_code: string, callback_url: string) =>
    request<PayLink>(`${V(id)}/pro`, { method: "POST", ...json({ plan_code, callback_url }) }, token),
  cancelPro: (token: string, id: string) => request<{ status: string }>(`${V(id)}/pro`, { method: "DELETE" }, token),
  featured: (token: string, id: string) => request<{ state: string; area: string | null; area_available: boolean;
    price_state_kobo: number; price_area_kobo: number;
    weeks: { week_start: string; state_left: number; area_left: number }[];
    mine: { id: string; scope: string; week_start: string; status: string }[] }>(`${V(id)}/featured`, {}, token),
  buyFeatured: (token: string, id: string, scope: "state" | "area", weeks: string[], callback_url: string) =>
    request<PayLink>(`${V(id)}/featured`, { method: "POST", ...json({ scope, weeks, callback_url }) }, token),
  analytics: (token: string, id: string) => request<Record<string, number | null>>(`${V(id)}/analytics`, {}, token),
  events: (token: string, id: string) => request<{ id: string; slug: string; title: string; start_date: string;
    status: string; review_status: string; attendees_count: number; members_only: boolean }[]>(`${V(id)}/events`, {}, token),
  createEvent: (token: string, id: string, body: Record<string, unknown>) =>
    request<{ id: string; slug: string; status: string; review_status: string }>(
      `${V(id)}/events`, { method: "POST", ...json(body) }, token),
};

// ── Agents ─────────────────────────────────────────────────────────────────────

export interface AgentVisitRow { id: string; status: string; scheduled_for: string | null; checked_in_at: string | null;
  venue: { id: string; name: string; address: string; state: string; area: string | null;
    latitude: number | null; longitude: number | null; phone: string | null } }

export interface KycDoc { id: string; kind: string; status: string; content_type: string;
  original_filename: string | null; rejection_reason: string | null; created_at: string; url: string }

export const agentApi = {
  me: (token: string) => request<{ user_id: string; states: string[]; phone: string | null;
    checklist: { id: string; label: string }[] }>("/agent/me", {}, token),
  visits: (token: string) => request<AgentVisitRow[]>("/agent/visits", {}, token),
  visit: (token: string, id: string) => request<{ id: string; status: string; scheduled_for: string | null;
    checked_in_at: string | null; distance_from_venue_m: number | null; checklist: Record<string, boolean>;
    notes: string | null; photos: string[]; documents: KycDoc[];
    venue: AgentVisitRow["venue"] & { type: string; legal_name: string | null; cac_number: string | null;
      description: string | null; spaces: Space[]; media: { kind: string; url: string }[] } }>(`/agent/visits/${id}`, {}, token),
  schedule: (token: string, id: string, scheduled_for: string) =>
    request<{ ok: boolean }>(`/agent/visits/${id}/schedule`, { method: "POST", ...json({ scheduled_for }) }, token),
  checkIn: (token: string, id: string, latitude: number, longitude: number, note?: string) =>
    request<{ distance_from_venue_m: number }>(`/agent/visits/${id}/check-in`, { method: "POST", ...json({ latitude, longitude, note }) }, token),
  photo: (token: string, id: string, file: File) => {
    const f = new FormData(); f.append("file", file);
    return upload<{ count: number }>(token, `/agent/visits/${id}/photos`, f);
  },
  report: (token: string, id: string, body: { checklist: Record<string, boolean>; notes: string; outcome: "passed" | "failed" }) =>
    request<{ status: string }>(`/agent/visits/${id}/report`, { method: "POST", ...json(body) }, token),
};

/** Signed KYC links are relative to the API origin. */
export const apiUrl = (path: string) => `${BASE}${path}`;

// ── Admin ──────────────────────────────────────────────────────────────────────

export const adminMarketApi = {
  overview: (token: string) => request<Record<string, number>>("/admin/marketplace-overview", {}, token),
  venues: (token: string, p: { status?: string; verification?: string; q?: string }) =>
    request<(VenueCard & { status: string; verification_status: string; pause_reason: string | null;
      area_other: string | null; created_at: string })[]>(`/admin/venues${qs(p)}`, {}, token),
  venue: (token: string, id: string) => request<any>(`/admin/venues/${id}`, {}, token),
  decideDoc: (token: string, id: string, docId: string, status: "approved" | "rejected", reason?: string) =>
    request<{ ok: boolean }>(`/admin/venues/${id}/documents/${docId}`, { method: "POST", ...json({ status, reason }) }, token),
  verify: (token: string, id: string, approve: boolean, note?: string) =>
    request<{ status: string }>(`/admin/venues/${id}/verification`, { method: "POST", ...json({ approve, note }) }, token),
  assign: (token: string, id: string, agent_id: string) =>
    request<{ ok: boolean }>(`/admin/venues/${id}/assign`, { method: "POST", ...json({ agent_id }) }, token),
  suspend: (token: string, id: string, suspend: boolean, note?: string) =>
    request<{ status: string }>(`/admin/venues/${id}/suspend`, { method: "POST", ...json({ suspend, note }) }, token),
  strike: (token: string, id: string, reason: string) =>
    request<{ strikes_last_year: number }>(`/admin/venues/${id}/strikes`, { method: "POST", ...json({ reason }) }, token),
  adjust: (token: string, id: string, amount_kobo: number, note: string) =>
    request<{ balance_kobo: number }>(`/admin/venues/${id}/ledger`, { method: "POST", ...json({ amount_kobo, note }) }, token),
  mapArea: (token: string, id: string, area_id: string) =>
    request<{ ok: boolean }>(`/admin/venues/${id}/area${qs({ area_id })}`, { method: "PUT" }, token),
  agents: (token: string) => request<{ user: UserBrief; states: string[]; phone: string | null; is_active: boolean;
    open_visits: number; completed_visits: number }[]>("/admin/agents", {}, token),
  upsertAgent: (token: string, body: { user_id: string; states: string[]; phone?: string; is_active: boolean }) =>
    request<{ ok: boolean }>("/admin/agents", { method: "PUT", ...json(body) }, token),
  disputes: (token: string, status = "open") => request<(Dispute & { evidence: string[]; booking: Booking })[]>(
    `/admin/venue-disputes${qs({ status })}`, {}, token),
  disputeThread: (token: string, id: string) => request<Enquiry>(`/admin/venue-disputes/${id}/thread`, {}, token),
  decideDispute: (token: string, id: string, body: { resolution: string; refund_kobo?: number | null; note: string }) =>
    request<{ status: string }>(`/admin/venue-disputes/${id}/decide`, { method: "POST", ...json(body) }, token),
  refunds: (token: string, status?: string) => request<(RefundRequest & { venue: { id: string; name: string } })[]>(
    `/admin/refund-requests${qs({ status })}`, {}, token),
  reports: (token: string) => request<{ id: string; status: string; details: string | null; enquiry_id: string;
    created_at: string; venue: { id: string; name: string } }[]>("/admin/off-platform-reports", {}, token),
  decideReport: (token: string, id: string, upheld: boolean, note?: string) =>
    request<{ status: string }>(`/admin/off-platform-reports/${id}`, { method: "POST", ...json({ upheld, note }) }, token),
  chargebacks: (token: string) => request<{ id: string; venue_id: string | null; reference: string | null;
    amount_kobo: number; status: string; created_at: string }[]>("/admin/chargebacks", {}, token),
  decideChargeback: (token: string, id: string, status: "won" | "lost") =>
    request<{ status: string }>(`/admin/chargebacks/${id}`, { method: "POST", ...json({ status }) }, token),
  areas: (token: string, state?: string) => request<{ areas: (Area & { is_active: boolean })[];
    unmapped: { venue_id: string; venue: string; state: string; typed: string }[] }>(`/admin/areas${qs({ state })}`, {}, token),
  addArea: (token: string, body: { state: string; name: string; kind: string }) =>
    request<{ id: string }>("/admin/areas", { method: "POST", ...json(body) }, token),
  editArea: (token: string, id: string, body: { name?: string; is_active?: boolean }) =>
    request<{ ok: boolean }>(`/admin/areas/${id}`, { method: "PATCH", ...json(body) }, token),
  settings: (token: string) => request<Record<string, number> & { plans: (Plan & { is_active: boolean })[] }>(
    "/admin/marketplace-settings", {}, token),
  saveSettings: (token: string, body: Record<string, number>) =>
    request<Record<string, number>>("/admin/marketplace-settings", { method: "PUT", ...json(body) }, token),
  setPlan: (token: string, code: string, amount_kobo: number, is_active: boolean) =>
    request<{ ok: boolean }>(`/admin/plans/${code}`, { method: "PUT", ...json({ amount_kobo, is_active }) }, token),
  featuredSlots: (token: string) => request<{ id: string; scope: string; state: string; area: string | null;
    week_start: string; status: string; amount_kobo: number; venue: { id: string; name: string } }[]>("/admin/featured-slots", {}, token),
  accessLog: (token: string, venue_id?: string) => request<{ at: string; action: string; venue_id: string | null;
    document_id: string | null; ip: string | null; user: UserBrief }[]>(`/admin/kyc-access-log${qs({ venue_id })}`, {}, token),
  hideReview: (token: string, id: string, is_hidden: boolean) =>
    request<{ ok: boolean }>(`/admin/venue-reviews/${id}`, { method: "PATCH", ...json({ is_hidden }) }, token),
};

// ── Turnup+ ────────────────────────────────────────────────────────────────────

export const plusApi = {
  plans: () => request<{ perks: Perk[]; plans: Plan[] }>("/plus/plans"),
  me: (token: string) => request<PlusMe>("/plus/me", {}, token),
  subscribe: (token: string, plan_code: string, callback_url: string) =>
    request<PayLink>("/plus/subscribe", { method: "POST", ...json({ plan_code, callback_url }) }, token),
  cancel: (token: string) => request<{ status: string; until: string | null }>("/plus", { method: "DELETE" }, token),
  settings: (token: string, body: { show_plus_badge?: boolean; wrapped_opt_in?: boolean }) =>
    request<{ show_plus_badge: boolean; wrapped_opt_in: boolean }>("/plus/settings", { method: "PATCH", ...json(body) }, token),
  myDeals: (token: string) => request<ClaimedDeal[]>("/me/deals", {}, token),
  claim: (token: string, dealId: string) =>
    request<{ code: string; claimed_at: string }>(`/deals/${dealId}/claim`, { method: "POST" }, token),
  eventDeals: (eventId: string) => request<Deal[]>(`/events/${eventId}/deals`),
  manageEventDeals: (token: string, eventId: string) => request<Deal[]>(`/events/${eventId}/deals/manage`, {}, token),
  createEventDeal: (token: string, eventId: string, body: Partial<Deal>) =>
    request<Deal>(`/events/${eventId}/deals`, { method: "POST", ...json(body) }, token),
  updateEventDeal: (token: string, eventId: string, dealId: string, body: Partial<Deal>) =>
    request<Deal>(`/events/${eventId}/deals/${dealId}`, { method: "PUT", ...json(body) }, token),
  redeemEventDeal: (token: string, eventId: string, code: string) =>
    request<{ ok: boolean; reason?: string; deal: string; member?: string }>(
      `/events/${eventId}/deals/redeem`, { method: "POST", ...json({ code }) }, token),
  transfer: (token: string, orderId: string, to_username: string) =>
    request<{ ok: boolean; to: string }>(`/tickets/${orderId}/transfer`, { method: "POST", ...json({ to_username }) }, token),
  weekend: (token: string) => request<WeekendPicks>("/me/weekend-picks", {}, token),
  wrapped: (token: string, year: number) => request<Wrapped>(`/me/wrapped/${year}`, {}, token),
  wrappedImageUrl: (year: number) => `${BASE}/api/me/wrapped/${year}/image.png`,
};

export function isPlus(user: { plus_until?: string | null } | null | undefined): boolean {
  return !!user?.plus_until && new Date(user.plus_until) > new Date();
}
