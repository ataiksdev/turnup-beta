export interface User {
  id: string;
  username: string;
  full_name: string;
  email?: string;
  role?: "attendee" | "organizer";
  bio?: string | null;
  avatar_url?: string | null;
  location?: string | null;
  website?: string | null;
  is_verified: boolean;
  is_active?: boolean;
  followers_count: number;
  following_count: number;
  events_hosted: number;
  events_attended: number;
  category_preferences?: string | null;
  onboarding_completed?: boolean;
  created_at?: string;
  is_following?: boolean;
}

export interface Category {
  id: string;
  name: string;
  slug: string;
  icon: string;
  color: string;
}

export interface Event {
  id: string;
  title: string;
  slug: string;
  description?: string;
  cover_image?: string | null;
  gallery?: string | string[] | null;
  venue_name: string;
  address: string;
  city: string;
  country: string;
  latitude?: number | null;
  longitude?: number | null;
  start_date: string;
  end_date: string;
  timezone?: string;
  is_free: boolean;
  price_min?: number | null;
  price_max?: number | null;
  currency: string;
  event_type?: "physical" | "virtual" | "hybrid";
  meeting_url?: string | null;
  capacity?: number | null;
  attendees_count: number;
  interested_count: number;
  saves_count: number;
  status: "draft" | "published" | "cancelled" | "completed";
  is_featured: boolean;
  is_trending: boolean;
  tags?: string | null;
  host: User;
  category?: Category | null;
  created_at: string;
  is_saved: boolean;
  attendance_status?: "going" | "interested" | null;
  waitlist_enabled?: boolean;
  waitlist_count?: number;
  is_waitlisted?: boolean;
}

export interface Comment {
  id: string;
  content: string;
  user: User;
  event_id: string;
  parent_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Notification {
  id: string;
  type: "follow" | "event_invite" | "event_reminder" | "comment" | "going" | "event_update";
  title: string;
  body?: string | null;
  reference_id?: string | null;
  reference_type?: string | null;
  actor?: { id: string; username: string; avatar_url?: string | null } | null;
  is_read: boolean;
  created_at: string;
}

export interface FeedItem {
  type: "attendance" | "follow";
  actor: User;
  status?: string;
  event?: Partial<Event>;
  target_user?: User;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface ApiError {
  detail: string;
}

export interface PaginatedParams {
  page?: number;
  limit?: number;
}

export interface EventFilters extends PaginatedParams {
  q?: string;
  tag?: string;
  city?: string;
  category?: string;
  event_type?: "physical" | "virtual" | "hybrid";
  featured?: boolean;
  trending?: boolean;
  free?: boolean;
}
