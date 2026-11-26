export interface User {
  id: string;
  username: string;
  full_name: string;
  display_name?: string | null;
  email?: string;
  role?: "attendee" | "organizer" | "moderator" | "admin";
  bio?: string | null;
  avatar_url?: string | null;
  location?: string | null;
  website?: string | null;
  is_verified: boolean;
  is_verified_organizer?: boolean;
  is_active?: boolean;
  followers_count: number;
  following_count: number;
  events_hosted: number;
  events_attended: number;
  avg_rating?: number | null;
  review_count?: number;
  category_preferences?: string | null;
  city?: string | null;
  price_sensitivity?: string | null;
  event_format_pref?: string | null;
  goes_out_when?: string | null;
  onboarding_completed?: boolean;
  email_verified?: boolean;
  two_factor_enabled?: boolean;
  has_password?: boolean;
  /** "<theme>:<mode>", e.g. "sunset:system" (see lib/themes.ts). */
  theme_preference?: string | null;
  /** Turnup+ membership end (null = not a member). */
  plus_until?: string | null;
  show_plus_badge?: boolean;
  wrapped_opt_in?: boolean;
  /** Data choices (docs/recommendations-spec.md). */
  birth_year?: number | null;
  gender?: "female" | "male" | "non_binary" | "prefer_not_to_say" | null;
  personalized_recs?: boolean;
  profiling_consent?: boolean;
  profiling_consent_at?: string | null;
  event_alerts?: boolean;
  /** Public profiles: a member who shows the badge. */
  plus_badge?: boolean;
  created_at?: string;
  is_following?: boolean;
  organizer_profile?: OrganizerProfile | null;
}

export interface OrganizerProfile {
  id: string;
  organization_name: string | null;
  organizer_bio: string | null;
  website: string | null;
  is_verified_organizer: boolean;
  verification_status: "none" | "pending" | "approved" | "rejected";
  verification_note: string | null;
  verification_requested_at: string | null;
  reviewed_at: string | null;
  created_at: string;
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
  series_id?: string | null;
  avg_rating?: number | null;
  review_count?: number;
  review_status?: "pending" | "approved" | "rejected";
  review_note?: string | null;
  created_via?: "manual" | "ai_agent" | "agent_api";
  refund_policy?: string | null;
  /** Venue marketplace: the venue hosting it, and the listed venue it takes place at. */
  host_venue_id?: string | null;
  venue_id?: string | null;
  /** Turnup+ options */
  members_only?: boolean;
  fast_lane_enabled?: boolean;
  allow_ticket_transfers?: boolean;
  following_count?: number;
  following_hosted?: boolean;
  /** GET /events/for-you only: why it was picked, and the id sent back with impressions/clicks. */
  rec_reason?: string | null;
  rec_request_id?: string | null;
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
  type: "follow" | "event_invite" | "event_reminder" | "comment" | "going" | "event_update"
    | "ticket_confirmed" | "ticket_refunded" | "ticket_cancelled"
    | "organizer_verified" | "organizer_verification_rejected";
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
  date_from?: string;
  date_to?: string;
  sort?: "date" | "relevance" | "popular" | "price_asc" | "price_desc" | "newest";
}
