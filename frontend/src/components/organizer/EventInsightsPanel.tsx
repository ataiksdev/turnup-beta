"use client";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, Lightbulb, Search, Tag, TrendingUp } from "lucide-react";
import { insightsApi, type EventInsights, type UnmetSearch } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { formatMoney } from "@/lib/utils";

const PARTS: Record<string, string> = { morning: "mornings", afternoon: "afternoons", evening: "evenings", late: "late nights" };
const DAY_NAMES: Record<string, string> = {
  Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday",
};

function Card({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="bg-bg-card border-2 border-border rounded p-4 shadow-brutal-sm space-y-2">
      <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-text-muted">
        {icon} {title}
      </p>
      {children}
    </div>
  );
}

function NotEnough({ children }: { children: ReactNode }) {
  return <p className="text-xs text-text-muted">{children}</p>;
}

function where(scope: "city" | "everywhere", city: string | null) {
  return scope === "city" && city ? `in ${city}` : "on Turnup";
}

function Pace({ c }: { c: EventInsights["booking_curve"] }) {
  const typical = c.points.some((p) => p.typical_share !== null);
  return (
    <Card icon={<TrendingUp size={14} className="text-primary" />} title="Booking pace">
      <div className="flex items-baseline gap-3">
        <span className="text-2xl font-black text-text">{c.so_far.toLocaleString()}</span>
        <span className="text-xs text-text-muted">going or bought so far</span>
      </div>
      {c.projected_total !== null && (
        <p className="text-sm text-text">
          On a typical pace that ends at about <strong>{c.projected_total.toLocaleString()}</strong>.
        </p>
      )}
      {typical ? (
        <table className="w-full text-xs">
          <caption className="sr-only">Your bookings and the typical share of final bookings, by days before the event</caption>
          <thead>
            <tr className="text-text-muted text-left">
              <th scope="col" className="font-bold py-1">Days before</th>
              <th scope="col" className="font-bold py-1 text-right">Yours</th>
              <th scope="col" className="font-bold py-1 text-right">Typical event, % of final</th>
            </tr>
          </thead>
          <tbody>
            {c.points.map((p) => (
              <tr key={p.days_before} className="border-t border-border">
                <td className="py-1 text-text">{p.days_before === 0 ? "On the day" : p.days_before}</td>
                <td className="py-1 text-right text-text">{p.yours === null ? "–" : p.yours.toLocaleString()}</td>
                <td className="py-1 text-right text-text-secondary">
                  {p.typical_share === null ? "–" : `${Math.round(p.typical_share * 100)}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <NotEnough>Not enough similar past events yet to show a typical pace.</NotEnough>
      )}
      {typical && <p className="text-[10px] text-text-muted">Typical pace from {c.comparables} similar past events.</p>}
    </Card>
  );
}

function Timing({ t, city }: { t: EventInsights["best_times"]; city: string | null }) {
  return (
    <Card icon={<CalendarClock size={14} className="text-primary" />} title="Best day and time">
      {!t ? (
        <NotEnough>Not enough similar past events yet.</NotEnough>
      ) : (
        <>
          <ol className="space-y-1">
            {t.best.map((b, i) => (
              <li key={`${b.day}${b.part}`} className="flex justify-between text-sm">
                <span className="text-text">{i + 1}. {DAY_NAMES[b.day]} {PARTS[b.part]}</span>
                <span className="text-text-secondary">{b.avg_turnout} going on average</span>
              </li>
            ))}
          </ol>
          <p className="text-xs text-text-muted">
            Yours is on a {DAY_NAMES[t.yours.day]} {t.yours.part}
            {t.yours.avg_turnout !== null ? `, where similar events average ${t.yours.avg_turnout}.` : "."}{" "}
            From similar events {where(t.scope, city)}.
          </p>
        </>
      )}
    </Card>
  );
}

function Price({ p, city }: { p: EventInsights["price"]; city: string | null }) {
  return (
    <Card icon={<Tag size={14} className="text-primary" />} title="Price">
      {!p || p.median === null ? (
        <NotEnough>Not enough paid events like this {p ? where(p.scope, city) : ""} to compare yet.</NotEnough>
      ) : (
        <>
          <p className="text-sm text-text">
            Similar events {where(p.scope, city)} usually start between <strong>{formatMoney(p.p25!)}</strong> and{" "}
            <strong>{formatMoney(p.p75!)}</strong> (middle: {formatMoney(p.median)}).
          </p>
          <p className="text-xs text-text-muted">
            {p.yours === null || p.yours === 0 ? "Yours is free." :
              `Yours starts at ${formatMoney(p.yours)}: ${p.position === "high" ? "higher than most" :
                p.position === "low" ? "lower than most" : "about typical"}.`}
            {p.free_share ? ` ${Math.round(p.free_share * 100)}% of them are free.` : ""}
          </p>
        </>
      )}
    </Card>
  );
}

export function UnmetSearchList({ searches, city }: { searches: UnmetSearch[]; city?: string | null }) {
  return (
    <Card icon={<Search size={14} className="text-primary" />} title={`Searched for${city ? ` in ${city}` : ""}, not found`}>
      {searches.length === 0 ? (
        <NotEnough>No unmet searches in the last 30 days.</NotEnough>
      ) : (
        <>
          <ul className="space-y-1">
            {searches.map((s) => (
              <li key={s.query} className="flex justify-between gap-3 text-sm">
                <span className="text-text truncate">&quot;{s.query}&quot;</span>
                <span className="shrink-0 text-text-secondary">{s.people} people</span>
              </li>
            ))}
          </ul>
          <p className="text-[10px] text-text-muted">Last 30 days, searches by at least 3 different people that found no events.</p>
        </>
      )}
    </Card>
  );
}

/** Analytics page: market context for one event (GET /events/{id}/insights). */
export function EventInsightsPanel({ eventId }: { eventId: string }) {
  const { token } = useAuthStore();
  const { data, isLoading } = useQuery({
    queryKey: ["insights", eventId], queryFn: () => insightsApi.event(token!, eventId),
    enabled: !!token && !!eventId, staleTime: 10 * 60_000,
  });
  if (isLoading || !data) return null;
  return (
    <section aria-labelledby="insights-heading" className="space-y-3">
      <h2 id="insights-heading" className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-text">
        <Lightbulb size={14} className="text-primary" aria-hidden /> Insights
        {data.category && <span className="text-text-muted normal-case font-bold tracking-normal">· {data.category}</span>}
      </h2>
      <Pace c={data.booking_curve} />
      <Timing t={data.best_times} city={data.city} />
      <Price p={data.price} city={data.city} />
      <UnmetSearchList searches={data.unmet_searches} city={data.city} />
    </section>
  );
}

/** Organizer dashboard: unmet demand across Turnup (or one city). */
export function UnmetSearchesCard({ city }: { city?: string | null }) {
  const { token } = useAuthStore();
  const { data } = useQuery({
    queryKey: ["insights", "searches", city ?? ""], queryFn: () => insightsApi.searches(token!, city ?? undefined),
    enabled: !!token, staleTime: 10 * 60_000,
  });
  if (!data) return null;
  return <UnmetSearchList searches={data.searches} city={data.city} />;
}
