"use client";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { formatPrice } from "@/lib/utils";
import { BarChart2, Eye, Heart, Bookmark, Ticket, TrendingUp, Users, Clock } from "lucide-react";
import Link from "next/link";

function StatCard({ icon, label, value, sub }: {
  icon: React.ReactNode; label: string; value: string | number; sub?: string;
}) {
  return (
    <div className="bg-bg-card border-2 border-border rounded p-4 shadow-brutal-sm space-y-1">
      <div className="flex items-center gap-2 text-text-muted mb-2">
        {icon}
        <span className="text-[10px] font-black uppercase tracking-widest">{label}</span>
      </div>
      <p className="text-2xl font-black text-text">{value}</p>
      {sub && <p className="text-xs text-text-muted">{sub}</p>}
    </div>
  );
}

export default function EventAnalyticsPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuthStore();

  const { data: event } = useQuery({
    queryKey: ["event", id],
    queryFn: () => eventsApi.get(id),
    enabled: !!id,
  });

  const { data: analytics, isLoading } = useQuery({
    queryKey: ["analytics", id],
    queryFn: () => eventsApi.analytics(token!, id),
    enabled: !!token && !!id,
  });

  const maxViews = analytics?.daily_views?.length
    ? Math.max(...analytics.daily_views.map((d) => d.views), 1)
    : 1;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-3 px-6 text-center">
        <span className="text-5xl">📊</span>
        <p className="text-text-secondary font-bold text-sm uppercase tracking-wide">
          No analytics yet
        </p>
        <Link href={`/organizer/events/${id}/edit`} className="text-primary text-sm font-medium hover:underline">
          ← Back to event
        </Link>
      </div>
    );
  }

  const conversionRate = analytics.total_views > 0
    ? ((analytics.rsvp_going / analytics.total_views) * 100).toFixed(1)
    : "0";

  return (
    <div className="flex flex-col min-h-screen bg-bg pb-8">
      <TopBar back title={event ? `Analytics · ${event.title}` : "Analytics"} />

      <div className="px-4 py-4 space-y-5">
        {/* Quick actions */}
        <div className="flex gap-2">
          <Link
            href={`/organizer/events/${id}/edit`}
            className="flex-1 py-2.5 text-center text-[10px] font-black uppercase tracking-widest rounded border-2 border-border bg-bg-card hover:border-primary transition-colors shadow-brutal-sm"
          >
            Edit Event
          </Link>
          <Link
            href={`/events/${id}`}
            className="flex-1 py-2.5 text-center text-[10px] font-black uppercase tracking-widest rounded border-2 border-border bg-bg-card hover:border-primary transition-colors shadow-brutal-sm"
          >
            View Page
          </Link>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 gap-3">
          <StatCard icon={<Eye size={14} />} label="Total Views" value={analytics.total_views.toLocaleString()} sub={`${analytics.unique_views.toLocaleString()} unique`} />
          <StatCard icon={<Users size={14} />} label="Going" value={analytics.rsvp_going.toLocaleString()} sub={`${conversionRate}% conversion`} />
          <StatCard icon={<Heart size={14} />} label="Interested" value={analytics.rsvp_interested.toLocaleString()} />
          <StatCard icon={<Bookmark size={14} />} label="Saved" value={analytics.saves_count.toLocaleString()} />
          <StatCard icon={<Ticket size={14} />} label="Tickets Sold" value={analytics.ticket_orders_count.toLocaleString()} />
          <StatCard
            icon={<TrendingUp size={14} />}
            label="Revenue"
            value={`$${analytics.estimated_revenue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          />
          {analytics.waitlist_count > 0 && (
            <StatCard icon={<Clock size={14} />} label="Waitlisted" value={analytics.waitlist_count.toLocaleString()} />
          )}
        </div>

        {/* Daily views bar chart */}
        {analytics.daily_views.length > 0 && (
          <div className="bg-bg-card border-2 border-border rounded p-4 shadow-brutal-sm">
            <div className="flex items-center gap-2 mb-4">
              <BarChart2 size={14} className="text-primary" />
              <p className="text-[10px] font-black uppercase tracking-widest text-text-muted">
                Daily Views · Last 14 Days
              </p>
            </div>
            <div className="flex items-end gap-1 h-28">
              {analytics.daily_views.map((d) => {
                const heightPct = Math.max(4, Math.round((d.views / maxViews) * 100));
                const label = new Date(d.date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
                return (
                  <div key={d.date} className="flex-1 flex flex-col items-center gap-1 group relative">
                    <div
                      className="w-full bg-primary rounded-t transition-all"
                      style={{ height: `${heightPct}%` }}
                    />
                    {/* tooltip on hover */}
                    <div className="absolute -top-7 left-1/2 -translate-x-1/2 bg-bg-elevated border border-border rounded px-1.5 py-0.5 text-[9px] font-bold text-text opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap transition-opacity z-10">
                      {d.views}
                    </div>
                  </div>
                );
              })}
            </div>
            {/* x-axis labels — show every ~3rd */}
            <div className="flex items-start gap-1 mt-1">
              {analytics.daily_views.map((d, i) => {
                const label = new Date(d.date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
                return (
                  <div key={d.date} className="flex-1 text-center">
                    {(i === 0 || i === Math.floor(analytics.daily_views.length / 2) || i === analytics.daily_views.length - 1) && (
                      <span className="text-[8px] text-text-muted">{label}</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Engagement summary */}
        <div className="bg-bg-card border-2 border-border rounded p-4 shadow-brutal-sm space-y-3">
          <p className="text-[10px] font-black uppercase tracking-widest text-text-muted">Engagement Breakdown</p>
          {[
            { label: "View → Interested", value: analytics.total_views > 0 ? ((analytics.rsvp_interested / analytics.total_views) * 100).toFixed(1) : "0", suffix: "%" },
            { label: "View → Going", value: conversionRate, suffix: "%" },
            { label: "View → Saved", value: analytics.total_views > 0 ? ((analytics.saves_count / analytics.total_views) * 100).toFixed(1) : "0", suffix: "%" },
          ].map(({ label, value, suffix }) => (
            <div key={label} className="flex items-center gap-3">
              <span className="text-xs text-text-muted w-36 shrink-0">{label}</span>
              <div className="flex-1 h-2 bg-border rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all"
                  style={{ width: `${Math.min(100, parseFloat(value))}%` }}
                />
              </div>
              <span className="text-xs font-bold text-text w-10 text-right">{value}{suffix}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
