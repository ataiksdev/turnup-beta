"use client";
import { useQuery } from "@tanstack/react-query";
import { Building2, CalendarCheck, ChevronRight, ClipboardCheck, MessageSquare, Sparkles } from "lucide-react";
import Link from "next/link";
import { agentApi, isPlus, portalApi } from "@/lib/marketplace";
import { publicOrigin, STATIC_EXPORT } from "@/lib/routes";
import { useAuthStore } from "@/store/auth";

function Row({ href, icon, label, hint, external }: { href: string; icon: React.ReactNode; label: string; hint?: string; external?: boolean }) {
  const inner = (
    <>
      <span className="text-primary">{icon}</span>
      <span className="flex-1"><span className="block text-sm font-bold text-text">{label}</span>
        {hint && <span className="block text-xs text-text-muted">{hint}</span>}</span>
      <ChevronRight size={16} className="text-text-muted" aria-hidden />
    </>
  );
  const cls = "flex items-center gap-3 py-2.5";
  return external
    ? <a href={href} target="_blank" rel="noopener noreferrer" className={cls}>{inner}</a>
    : <Link href={href} className={cls}>{inner}</Link>;
}

/** Turnup+, venue bookings, and (web-only) the venue and agent portals. */
export function MarketplaceLinks() {
  const { token, user } = useAuthStore();
  const venues = useQuery({ queryKey: ["portal", "mine"], queryFn: () => portalApi.myVenues(token!), enabled: !!token, retry: false });
  const agent = useQuery({ queryKey: ["agent", "me"], queryFn: () => agentApi.me(token!), enabled: !!token, retry: false });
  if (!user) return null;
  const isOrganizer = ["organizer", "admin", "moderator"].includes(user.role ?? "");
  // The venue and agent portals are web-only (not in the Android app).
  const web = (path: string) => (STATIC_EXPORT ? `${publicOrigin()}${path}` : path);
  return (
    <section className="border-2 border-border rounded bg-bg-card p-4 divide-y-2 divide-border-subtle">
      <Row href="/plus" icon={<Sparkles size={18} />} label="Turnup+"
        hint={isPlus(user) ? "You're a member" : "Presale, priority waitlist, deals and more"} />
      {isOrganizer && <Row href="/enquiries" icon={<MessageSquare size={18} />} label="Venue enquiries" />}
      {isOrganizer && <Row href="/venue-bookings" icon={<CalendarCheck size={18} />} label="Venue bookings" />}
      <Row href={web("/venue")} external={STATIC_EXPORT} icon={<Building2 size={18} />}
        label={venues.data?.length ? "Venue portal" : "List your venue"}
        hint={venues.data?.length ? `${venues.data.length} venue${venues.data.length > 1 ? "s" : ""}` : "On the Turnup website"} />
      {agent.isSuccess && <Row href={web("/agent")} external={STATIC_EXPORT} icon={<ClipboardCheck size={18} />} label="Agent visits" />}
    </section>
  );
}
