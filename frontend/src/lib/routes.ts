/**
 * In-app links to pages that take an id/slug/username.
 *
 * The web build serves real dynamic routes (/events/abc). The Capacitor (Android) build is a
 * static export, and a static export only contains pages known at build time, so
 * /events/abc has no HTML file in the app bundle and can't load. There, the same screens
 * live at fixed paths that read the value from the query string (/events/view?id=abc).
 * Every in-app link goes through these helpers so each build gets the right form.
 *
 * Links meant for OUTSIDE the app (share buttons, emails, invite links) should keep using the
 * public web URL, not these helpers.
 */
export const STATIC_EXPORT = process.env.NEXT_PUBLIC_STATIC_EXPORT === "true";

// Accepts a possibly-missing value (some API fields are optional) like the template strings
// these helpers replaced did.
type Id = string | null | undefined;
const enc = (v: Id) => encodeURIComponent(v ?? "");

function path(web: string, mobile: string, query: Record<string, Id>) {
  if (!STATIC_EXPORT) return web;
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) q.set(k, v ?? "");
  return `${mobile}?${q.toString()}`;
}

type OrganizerSection = "edit" | "analytics" | "checkin" | "cohosts";

export const routes = {
  event: (id: Id) => path(`/events/${enc(id)}`, "/events/view", { id }),
  // "by-name", not "view": a user may be called "view", but usernames can't contain "-".
  profile: (username: Id) => path(`/profile/${enc(username)}`, "/profile/by-name", { username }),
  community: (slug: Id) => path(`/communities/${enc(slug)}`, "/communities/view", { slug }),
  communitySettings: (slug: Id) =>
    path(`/communities/${enc(slug)}/settings`, "/communities/view/settings", { slug }),
  communityInvite: (token: Id) =>
    path(`/communities/join/${enc(token)}`, "/communities/join/view", { token }),
  ticket: (id: Id) => path(`/tickets/${enc(id)}`, "/tickets/view", { id }),
  organizerEvent: (id: Id, section: OrganizerSection) =>
    path(`/organizer/events/${enc(id)}/${section}`, `/organizer/events/view/${section}`, { id }),
  series: (id: Id) => path(`/organizer/series/${enc(id)}`, "/organizer/series/view", { id }),
  venue: (slug: Id) => path(`/venues/${enc(slug)}`, "/venues/view", { slug }),
  enquiry: (id: Id) => path(`/enquiries/${enc(id)}`, "/enquiries/view", { id }),
  venueBooking: (id: Id) => path(`/venue-bookings/${enc(id)}`, "/venue-bookings/view", { id }),
};

/** Origin for links that leave the app (share buttons, invite links). In the Android app
 *  window.location.origin is the WebView's own http://localhost, so those links must use the
 *  public site URL (NEXT_PUBLIC_SITE_URL, set it for the Capacitor build). */
export function publicOrigin(): string {
  const configured = process.env.NEXT_PUBLIC_SITE_URL;
  if (configured) return configured.replace(/\/+$/, "");
  return typeof window !== "undefined" ? window.location.origin : "";
}
