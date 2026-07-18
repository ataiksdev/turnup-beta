import type {
  Category, Comment, Event, EventFilters, FeedItem,
  Notification, Token, User,
} from "@/types";

export interface TicketTierDetail {
  id: string; event_id: string; name: string; description: string | null;
  price: number; currency: string; quantity: number | null; quantity_sold: number;
  available: number | null; max_per_order: number; is_active: boolean;
  sale_start: string | null; sale_end: string | null; created_at: string;
}

export interface TicketOrder {
  id: string; event_id: string; tier_id: string; tier_name: string;
  quantity: number; unit_price: number; total_price: number;
  status: string; payment_reference?: string; created_at: string;
  event_title?: string; event_slug?: string; event_cover?: string;
  event_date?: string; event_city?: string;
}

export interface PaymentInit {
  order_id: string;
  payment_reference: string;
  paystack_public_key: string;
  amount_kobo: number;
  email: string;
  is_free: boolean;
}

export interface DailyView { date: string; views: number; }
export interface EventAnalytics {
  event_id: string; total_views: number; unique_views: number;
  rsvp_going: number; rsvp_interested: number; saves_count: number;
  waitlist_count: number; ticket_orders_count: number; estimated_revenue: number;
  daily_views: DailyView[];
}

export interface Review {
  id: string; event_id: string; user_id: string; username: string;
  full_name: string; avatar_url: string | null; rating: number;
  body: string | null; created_at: string;
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}/api${path}`, { ...options, headers });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, err.detail ?? "Request failed");
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Auth ───────────────────────────────────────────────────────────────────────

type OAuthCallbackResult = {
  access_token?: string;
  token_type?: string;
  expires_in?: number;
  requires_email?: boolean;
  partial_token?: string;
};

export const authApi = {
  register: (data: { email: string; username: string; full_name: string; password: string }) =>
    request<Token>("/auth/register", { method: "POST", body: JSON.stringify(data) }),

  login: (identifier: string, password: string) =>
    request<Token>("/auth/login", { method: "POST", body: JSON.stringify({ identifier, password }) }),

  me: (token: string) =>
    request<User>("/auth/me", {}, token),

  updateMe: (token: string, data: Partial<User>) =>
    request<User>("/auth/me", { method: "PATCH", body: JSON.stringify(data) }, token),

  completeOnboarding: (token: string, categoryPreferences: string[]) =>
    request<{ onboarding_completed: boolean; category_preferences: string }>(
      "/auth/onboarding",
      { method: "POST", body: JSON.stringify({ category_preferences: categoryPreferences }) },
      token,
    ),

  getOAuthUrl: (provider: "google" | "instagram") =>
    request<{ url: string }>(`/auth/oauth/${provider}`),

  oauthCallback: (provider: string, code: string, state: string) =>
    request<OAuthCallbackResult>(`/auth/oauth/${provider}/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`),

  oauthComplete: (partialToken: string, email: string) =>
    request<Token>("/auth/oauth/complete", {
      method: "POST",
      body: JSON.stringify({ partial_token: partialToken, email }),
    }),

  phoneRequestOtp: (phoneNumber: string) =>
    request<{ message: string }>("/auth/phone/send-otp", {
      method: "POST",
      body: JSON.stringify({ phone_number: phoneNumber }),
    }),

  phoneVerify: (phoneNumber: string, otpCode: string) =>
    request<Token>("/auth/phone/verify", {
      method: "POST",
      body: JSON.stringify({ phone_number: phoneNumber, otp_code: otpCode }),
    }),
};

// ── Events ─────────────────────────────────────────────────────────────────────
export const eventsApi = {
  list: (filters: EventFilters = {}, token?: string) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null) params.set(k, String(v));
    });
    return request<Event[]>(`/events?${params}`, {}, token);
  },

  trending: (limit = 10, token?: string) =>
    request<Event[]>(`/events/trending?limit=${limit}`, {}, token),

  featured: (limit = 6, token?: string) =>
    request<Event[]>(`/events/featured?limit=${limit}`, {}, token),

  forYou: (limit = 20, token?: string) =>
    request<Event[]>(`/events/for-you?limit=${limit}`, {}, token),

  get: (idOrSlug: string, token?: string) =>
    request<Event>(`/events/${idOrSlug}`, {}, token),

  create: (token: string, data: Partial<Event>) =>
    request<Event>("/events", { method: "POST", body: JSON.stringify(data) }, token),

  update: (token: string, eventId: string, data: Partial<Event>) =>
    request<Event>(`/events/${eventId}`, { method: "PATCH", body: JSON.stringify(data) }, token),

  tiers: (eventId: string) =>
    request<TicketTierDetail[]>(`/events/${eventId}/tickets`),

  createTier: (token: string, eventId: string, data: {
    name: string; description?: string; price: number; currency?: string;
    quantity?: number | null; max_per_order?: number; is_active?: boolean;
    sale_start?: string | null; sale_end?: string | null;
  }) =>
    request<{ id: string; name: string; price: number }>(`/events/${eventId}/tickets`, {
      method: "POST", body: JSON.stringify(data),
    }, token),

  attend: (token: string, eventId: string, status: "going" | "interested") =>
    request<{ status: string; attendees_count: number }>(
      `/events/${eventId}/attend`,
      { method: "POST", body: JSON.stringify({ status }) },
      token,
    ),

  removeAttendance: (token: string, eventId: string) =>
    request<{ status: null }>(`/events/${eventId}/attend`, { method: "DELETE" }, token),

  save: (token: string, eventId: string) =>
    request<{ saved: boolean }>(`/events/${eventId}/save`, { method: "POST" }, token),

  attendees: (eventId: string, status?: string) => {
    const q = status ? `?status=${status}` : "";
    return request<{ user_id: string; status: string; created_at: string }[]>(
      `/events/${eventId}/attendees${q}`,
    );
  },

  categories: () => request<Category[]>("/categories"),

  analytics: (token: string, eventId: string) =>
    request<EventAnalytics>(`/events/${eventId}/analytics`, {}, token),

  initPayment: (token: string, eventId: string, tierId: string, quantity: number) =>
    request<PaymentInit>(`/events/${eventId}/tickets/${tierId}/purchase`, {
      method: "POST", body: JSON.stringify({ quantity }),
    }, token),

  verifyPayment: (token: string, eventId: string, tierId: string, reference: string) =>
    request<TicketOrder>(`/events/${eventId}/tickets/${tierId}/verify-payment`, {
      method: "POST", body: JSON.stringify({ reference }),
    }, token),

  waitlistJoin: (token: string, eventId: string) =>
    request<{ status: string; position: number; waitlist_count: number }>(
      `/events/${eventId}/waitlist`, { method: "POST" }, token),

  waitlistLeave: (token: string, eventId: string) =>
    request<void>(`/events/${eventId}/waitlist`, { method: "DELETE" }, token),

  reviews: (eventId: string) =>
    request<Review[]>(`/events/${eventId}/reviews`),

  myReview: (token: string, eventId: string) =>
    request<Review | null>(`/events/${eventId}/reviews/me`, {}, token),

  createReview: (token: string, eventId: string, rating: number, body?: string) =>
    request<Review>(`/events/${eventId}/reviews`, {
      method: "POST", body: JSON.stringify({ rating, body }),
    }, token),

  deleteReview: (token: string, eventId: string) =>
    request<void>(`/events/${eventId}/reviews/me`, { method: "DELETE" }, token),
};

// ── Users ──────────────────────────────────────────────────────────────────────
export const usersApi = {
  get: (username: string, token?: string) =>
    request<User>(`/users/${username}`, {}, token),

  events: (username: string, past = false, page = 1) =>
    request<Event[]>(`/users/${username}/events?past=${past}&page=${page}`),

  attending: (username: string, token: string, past = false, page = 1) =>
    request<Event[]>(`/users/${username}/attending?past=${past}&page=${page}`, {}, token),

  saved: (username: string, token: string, page = 1) =>
    request<Event[]>(`/users/${username}/saved?page=${page}`, {}, token),

  followers: (username: string) =>
    request<User[]>(`/users/${username}/followers`),

  following: (username: string) =>
    request<User[]>(`/users/${username}/following`),
};

// ── Organizer ─────────────────────────────────────────────────────────────────

export interface OrganizerDashboard {
  total_events: number;
  published_events: number;
  draft_events: number;
  total_attendees: number;
  total_revenue: number;
  pending_cohost_invites: number;
}

export interface CoHostInvite {
  id: string;
  event_id: string;
  event_title: string;
  event_start: string | null;
  status: string;
  invited_at: string;
}

export interface OrganizerOrder {
  id: string; event_id: string; tier_id: string; tier_name: string;
  buyer_username: string; buyer_email: string;
  quantity: number; unit_price: number; total_price: number;
  status: string; created_at: string;
}

export interface EventTemplate {
  id: string; organizer_id: string; name: string;
  description: string | null; template_data: Record<string, unknown>;
  created_at: string; updated_at: string;
}

export interface CoHost {
  id: string; user_id: string; username: string; full_name: string;
  avatar_url: string | null; status: string;
  invited_at: string; responded_at: string | null;
}

export const organizerApi = {
  become: (token: string, data: { organization_name?: string; organizer_bio?: string; website?: string }) =>
    request<User>("/organizer/become", { method: "POST", body: JSON.stringify(data) }, token),

  dashboard: (token: string) =>
    request<OrganizerDashboard>("/organizer/dashboard", {}, token),

  myEvents: (token: string) =>
    request<Event[]>("/organizer/events?limit=50", {}, token),

  myTickets: (token: string) =>
    request<TicketOrder[]>("/organizer/my-tickets", {}, token),

  cohostInvites: (token: string) =>
    request<CoHostInvite[]>("/organizer/cohost-invites", {}, token),

  respondCohost: (token: string, eventId: string, accept: boolean) =>
    request<{ status: string }>(`/events/${eventId}/cohosts/respond`, {
      method: "POST", body: JSON.stringify({ accept }),
    }, token),

  orders: (token: string, eventId?: string, page = 1) => {
    const params = new URLSearchParams({ page: String(page), limit: "50" });
    if (eventId) params.set("event_id", eventId);
    return request<OrganizerOrder[]>(`/organizer/orders?${params}`, {}, token);
  },

  // Templates
  listTemplates: (token: string) =>
    request<EventTemplate[]>("/organizer/templates", {}, token),

  createTemplate: (token: string, data: { name: string; description?: string; template_data: Record<string, unknown> }) =>
    request<EventTemplate>("/organizer/templates", { method: "POST", body: JSON.stringify(data) }, token),

  updateTemplate: (token: string, id: string, data: { name?: string; description?: string; template_data?: Record<string, unknown> }) =>
    request<EventTemplate>(`/organizer/templates/${id}`, { method: "PATCH", body: JSON.stringify(data) }, token),

  deleteTemplate: (token: string, id: string) =>
    request<void>(`/organizer/templates/${id}`, { method: "DELETE" }, token),

  // Co-hosts
  listCohosts: (eventId: string) =>
    request<CoHost[]>(`/events/${eventId}/cohosts`),

  inviteCohost: (token: string, eventId: string, username: string) =>
    request<CoHost>(`/events/${eventId}/cohosts`, {
      method: "POST", body: JSON.stringify({ username }),
    }, token),

  removeCohost: (token: string, eventId: string, cohostUserId: string) =>
    request<void>(`/events/${eventId}/cohosts/${cohostUserId}`, { method: "DELETE" }, token),
};

// ── Series ─────────────────────────────────────────────────────────────────────

export interface EventSeries {
  id: string;
  title: string;
  description: string | null;
  recurrence_rule: "weekly" | "bi-weekly" | "monthly" | "bi-monthly";
  organizer_id: string;
  created_at: string;
  events: Array<{
    id: string; title: string; slug: string;
    start_date: string; end_date: string;
    status: string; attendees_count: number;
  }>;
}

export const seriesApi = {
  create: (token: string, data: {
    title: string; description?: string;
    recurrence_rule: string; occurrences: number;
    event_title: string; event_description: string;
    cover_image?: string; event_type?: string;
    meeting_url?: string; venue_name: string;
    address: string; city: string; country?: string;
    timezone?: string; capacity?: number;
    waitlist_enabled?: boolean; is_free?: boolean;
    price_min?: number; price_max?: number; currency?: string;
    tags?: string; category_id?: string;
    start_date: string; end_date: string; status?: string;
  }) =>
    request<EventSeries>("/series", { method: "POST", body: JSON.stringify(data) }, token),

  get: (id: string) =>
    request<EventSeries>(`/series/${id}`),

  delete: (token: string, id: string) =>
    request<void>(`/series/${id}`, { method: "DELETE" }, token),
};

// ── Social ─────────────────────────────────────────────────────────────────────
export const socialApi = {
  follow: (token: string, username: string) =>
    request<{ following: boolean }>(`/social/follow/${username}`, { method: "POST" }, token),

  unfollow: (token: string, username: string) =>
    request<{ following: boolean }>(`/social/follow/${username}`, { method: "DELETE" }, token),

  comments: (eventId: string, page = 1) =>
    request<Comment[]>(`/social/events/${eventId}/comments?page=${page}`),

  addComment: (token: string, eventId: string, content: string, parentId?: string) =>
    request<Comment>(
      `/social/events/${eventId}/comments`,
      { method: "POST", body: JSON.stringify({ content, parent_id: parentId }) },
      token,
    ),

  deleteComment: (token: string, commentId: string) =>
    request<void>(`/social/comments/${commentId}`, { method: "DELETE" }, token),

  notifications: (token: string, unreadOnly = false) =>
    request<Notification[]>(`/social/notifications?unread_only=${unreadOnly}`, {}, token),

  markRead: (token: string, notificationId: string) =>
    request<{ ok: boolean }>(`/social/notifications/${notificationId}/read`, { method: "POST" }, token),

  markAllRead: (token: string) =>
    request<{ ok: boolean }>("/social/notifications/read-all", { method: "POST" }, token),

  feed: (token: string, page = 1) =>
    request<FeedItem[]>(`/social/feed?page=${page}`, {}, token),
};

// ── Admin ──────────────────────────────────────────────────────────────────────

export interface AdminUserOut {
  id: string; username: string; full_name: string | null; display_name: string | null;
  email: string | null; role: string; is_active: boolean; is_verified: boolean;
  email_verified: boolean; followers_count: number; following_count: number;
  events_hosted: number; events_attended: number; created_at: string;
}

export interface AdminEventOut {
  id: string; title: string; slug: string; status: string;
  is_featured: boolean; is_trending: boolean; event_type: string;
  city: string; country: string; start_date: string;
  attendees_count: number; views_count: number;
  host_username: string; host_id: string; created_at: string;
}

export interface AdminCategoryOut {
  id: string; name: string; slug: string; icon: string; color: string;
  description: string | null;
}

export interface AdminOrderOut {
  id: string; event_id: string; event_title: string; tier_name: string;
  buyer_username: string; buyer_email: string | null;
  quantity: number; unit_price: number; total_price: number;
  currency: string; status: string; created_at: string;
}

export interface PlatformStats {
  total_users: number; total_organizers: number; total_events: number;
  published_events: number; total_orders: number; confirmed_revenue: number;
  total_attendees: number; new_users_this_week: number; new_events_this_week: number;
}

export const adminApi = {
  stats: (token: string) =>
    request<PlatformStats>("/admin/stats", {}, token),

  users: (token: string, params?: { q?: string; role?: string; skip?: number }) => {
    const qs = new URLSearchParams();
    if (params?.q) qs.set("q", params.q);
    if (params?.role) qs.set("role", params.role);
    if (params?.skip) qs.set("skip", String(params.skip));
    return request<AdminUserOut[]>(`/admin/users?${qs}`, {}, token);
  },

  updateUser: (token: string, userId: string, body: { role?: string; is_active?: boolean; is_verified?: boolean }) =>
    request<AdminUserOut>(`/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(body) }, token),

  events: (token: string, params?: { q?: string; status?: string; skip?: number }) => {
    const qs = new URLSearchParams();
    if (params?.q) qs.set("q", params.q);
    if (params?.status) qs.set("status", params.status);
    if (params?.skip) qs.set("skip", String(params.skip));
    return request<AdminEventOut[]>(`/admin/events?${qs}`, {}, token);
  },

  updateEvent: (token: string, eventId: string, body: { is_featured?: boolean; is_trending?: boolean; status?: string }) =>
    request<AdminEventOut>(`/admin/events/${eventId}`, { method: "PATCH", body: JSON.stringify(body) }, token),

  categories: (token: string) =>
    request<AdminCategoryOut[]>("/admin/categories", {}, token),

  createCategory: (token: string, body: { name: string; slug: string; icon: string; color: string; description?: string }) =>
    request<AdminCategoryOut>("/admin/categories", { method: "POST", body: JSON.stringify(body) }, token),

  updateCategory: (token: string, catId: string, body: Partial<{ name: string; slug: string; icon: string; color: string; description: string }>) =>
    request<AdminCategoryOut>(`/admin/categories/${catId}`, { method: "PATCH", body: JSON.stringify(body) }, token),

  deleteCategory: (token: string, catId: string) =>
    request<void>(`/admin/categories/${catId}`, { method: "DELETE" }, token),

  orders: (token: string, params?: { skip?: number }) => {
    const qs = new URLSearchParams();
    if (params?.skip) qs.set("skip", String(params.skip));
    return request<AdminOrderOut[]>(`/admin/orders?${qs}`, {}, token);
  },
};
