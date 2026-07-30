"use client";
import { useQuery } from "@tanstack/react-query";
import { organizerApi, usersApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { EventCard } from "@/components/events/EventCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";
import { CalendarPlus, TrendingUp, Users, DollarSign, FileText, Ticket } from "lucide-react";
import Link from "next/link";
import { cn, displayName } from "@/lib/utils";

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <div className={cn(
      "flex flex-col gap-1.5 p-4 rounded border-2 border-border bg-bg-card shadow-brutal",
    )}>
      <div className={cn("w-8 h-8 rounded flex items-center justify-center border-2 border-border", color)}>
        <Icon size={16} className="text-white" aria-hidden />
      </div>
      <span className="text-2xl font-black text-text">{value}</span>
      <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">{label}</span>
    </div>
  );
}

export default function OrganizerDashboardPage() {
  const { token, user } = useAuthStore();

  const { data: stats, isLoading: loadingStats } = useQuery({
    queryKey: ["organizer", "dashboard"],
    queryFn: () => organizerApi.dashboard(token!),
    enabled: !!token,
  });

  const { data: events, isLoading: loadingEvents } = useQuery({
    queryKey: ["user-events", user?.username],
    queryFn: () => usersApi.events(user!.username),
    enabled: !!user?.username,
  });

  const recentEvents = events?.slice(0, 6);

  return (
    <div className="flex flex-col pb-4">
      <TopBar />

      {/* Greeting */}
      <div className="px-4 py-4 space-y-1">
        <span className="text-xs font-black text-primary uppercase tracking-widest">Organizer Dashboard</span>
        <h1 className="text-2xl font-black text-text">
          {user ? displayName(user).split(" ")[0] : "Hey"}
        </h1>
        <p className="text-xs font-bold text-text-muted uppercase tracking-widest">
          Here's how your events are doing
        </p>
      </div>

      {/* Stats grid */}
      <div className="px-4 mb-6">
        {loadingStats ? (
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full" />
            ))}
          </div>
        ) : stats ? (
          <div className="grid grid-cols-2 gap-3">
            <StatCard icon={CalendarPlus}  label="Total Events"    value={stats.total_events}    color="bg-primary" />
            <StatCard icon={TrendingUp}    label="Published"       value={stats.published_events} color="bg-success" />
            <StatCard icon={Users}         label="Total Attendees" value={stats.total_attendees}  color="bg-[#3B82F6]" />
            <StatCard icon={DollarSign}    label="Net Payout"      value={`₦${stats.net_revenue.toLocaleString()}`} color="bg-[#A855F7]" />
          </div>
        ) : null}
      </div>

      {/* Revenue breakdown */}
      {stats && stats.total_revenue > 0 && (
        <div className="px-4 mb-6 -mt-2">
          <p className="text-xs text-text-muted">
            ₦{stats.total_revenue.toLocaleString()} gross ticket sales · −₦{stats.platform_fee_total.toLocaleString()} platform fee
          </p>
        </div>
      )}

      {/* Draft events alert */}
      {stats && stats.draft_events > 0 && (
        <div className="mx-4 mb-5 flex items-center justify-between p-4 rounded border-2 border-border bg-bg-card shadow-brutal-sm">
          <div className="flex items-center gap-3">
            <FileText size={18} className="text-text-muted shrink-0" />
            <div>
              <p className="text-sm font-black text-text">
                {stats.draft_events} draft event{stats.draft_events !== 1 ? "s" : ""}
              </p>
              <p className="text-xs text-text-muted">Not yet published</p>
            </div>
          </div>
          <Link href="/organizer/events">
            <Button variant="secondary" size="sm">View</Button>
          </Link>
        </div>
      )}

      {/* Create event CTA */}
      <div className="px-4 mb-6">
        <Link
          href="/organizer/create"
          className="flex items-center justify-between p-5 rounded border-2 border-primary bg-primary/10 shadow-brutal hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-lg transition-all duration-100 active:translate-x-0.5 active:translate-y-0.5 active:shadow-none"
        >
          <div className="space-y-0.5">
            <p className="font-black text-primary text-sm uppercase tracking-wide">Create New Event</p>
            <p className="text-xs text-text-muted">Publish, set tickets, invite co-hosts</p>
          </div>
          <CalendarPlus size={28} className="text-primary shrink-0" />
        </Link>
      </div>

      {/* Recent events */}
      <section className="space-y-3">
        <div className="flex items-center justify-between px-4">
          <h2 className="text-xs font-black text-text uppercase tracking-widest">Your Events</h2>
          {events && events.length > 6 && (
            <Link href="/organizer/events" className="text-[10px] font-black text-primary uppercase tracking-widest">
              See all
            </Link>
          )}
        </div>

        {loadingEvents ? (
          <div className="snap-scroll px-4 pb-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="w-44 h-64 shrink-0" />
            ))}
          </div>
        ) : recentEvents && recentEvents.length > 0 ? (
          <div className="snap-scroll px-4 pb-2">
            {recentEvents.map((e) => (
              <EventCard key={e.id} event={e} size="md" />
            ))}
          </div>
        ) : (
          <div className="mx-4 flex flex-col items-center justify-center py-12 gap-3 border-2 border-dashed border-border rounded">
            <Ticket size={36} className="text-border-strong" aria-hidden />
            <p className="text-sm font-black text-text-secondary uppercase tracking-wide">No events yet</p>
            <Link href="/organizer/create">
              <Button size="sm">Create your first event</Button>
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}
