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
  status: string; created_at: string;
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

  login: (email: string, password: string) =>
    request<Token>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

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

  purchase: (token: string, eventId: string, tierId: string, quantity: number) =>
    request<TicketOrder>(`/events/${eventId}/tickets/${tierId}/purchase`, {
      method: "POST", body: JSON.stringify({ quantity }),
    }, token),

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

export const organizerApi = {
  become: (token: string, data: { organization_name?: string; organizer_bio?: string; website?: string }) =>
    request<User>("/organizer/become", { method: "POST", body: JSON.stringify(data) }, token),

  dashboard: (token: string) =>
    request<OrganizerDashboard>("/organizer/dashboard", {}, token),

  myEvents: (token: string) =>
    request<Event[]>("/organizer/events?limit=50", {}, token),
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
