"use client";
import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity as ActivityIcon, Clock, Database, MousePointerClick, Search, Sparkles } from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import { dataHealthApi, type DataHealth } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { cn } from "@/lib/utils";

function Panel({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="bg-bg-card border-2 border-border rounded p-4 shadow-brutal-sm space-y-3">
      <h2 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-text-muted">{icon} {title}</h2>
      {children}
    </section>
  );
}

function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-widest text-text-muted">{label}</p>
      <p className="text-xl font-black text-text">{value}</p>
      {sub && <p className="text-[10px] text-text-muted">{sub}</p>}
    </div>
  );
}

/** One series of bars. Values show on hover (title) and in the table below. */
function Bars({ items, label }: { items: { key: string; value: number; tip: string; tick?: string }[]; label: string }) {
  const max = Math.max(Number.EPSILON, ...items.map((i) => i.value));  // tallest bar fills the plot
  return (
    <figure aria-label={label}>
      <div className="flex items-end gap-[2px] h-28 border-b border-border">
        {items.map((i) => (
          <div key={i.key} title={i.tip} className="flex-1 h-full flex items-end group">
            <div className="w-full bg-primary rounded-t-[4px] group-hover:opacity-80"
              style={{ height: `${i.value ? Math.max(3, (i.value / max) * 100) : 0}%` }} />
          </div>
        ))}
      </div>
      <div className="flex gap-[2px] mt-1">
        {items.map((i) => (
          <span key={i.key} className="flex-1 text-center text-[8px] text-text-muted whitespace-nowrap">{i.tick ?? ""}</span>
        ))}
      </div>
    </figure>
  );
}

function ago(iso: string | null) {
  return iso ? `${formatDistanceToNow(new Date(iso))} ago` : "never";
}

function secs(s: number | null) {
  if (s === null) return "–";
  return s < 120 ? `${s.toFixed(0)}s` : s < 7200 ? `${(s / 60).toFixed(0)}m` : `${(s / 3600).toFixed(1)}h`;
}

function pct(x: number | null) {
  return x === null ? "–" : `${(x * 100).toFixed(1)}%`;
}

function Volume({ d }: { d: DataHealth }) {
  const days = d.events_per_day;
  return (
    <Panel icon={<ActivityIcon size={14} className="text-primary" />} title={`Events recorded per day · last ${d.days} days`}>
      <Bars label="Events recorded per day" items={days.map((x, i) => ({
        key: x.date, value: x.client + x.server,
        tip: `${x.date}: ${x.client.toLocaleString()} from the app, ${x.server.toLocaleString()} from the server`,
        tick: i === 0 || i === days.length - 1 || i === Math.floor(days.length / 2) ? format(new Date(`${x.date}T00:00:00`), "d MMM") : undefined,
      }))} />
      <details className="text-xs">
        <summary className="cursor-pointer text-text-muted">Table</summary>
        <table className="w-full mt-2">
          <thead><tr className="text-text-muted text-left"><th className="py-1">Day</th><th className="text-right">App</th><th className="text-right">Server</th></tr></thead>
          <tbody>{days.map((x) => (
            <tr key={x.date} className="border-t border-border"><td className="py-1">{x.date}</td>
              <td className="text-right">{x.client.toLocaleString()}</td><td className="text-right">{x.server.toLocaleString()}</td></tr>
          ))}</tbody>
        </table>
      </details>
      {d.top_events_24h.length > 0 && (
        <div className="text-xs">
          <p className="font-bold text-text mb-1">Most recorded, last 24 hours</p>
          <ul className="grid grid-cols-2 gap-x-4 gap-y-0.5">
            {d.top_events_24h.map((e) => (
              <li key={e.name} className="flex justify-between gap-2"><span className="text-text-secondary truncate">{e.name}</span><span className="text-text">{e.count.toLocaleString()}</span></li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

function Positions({ d }: { d: DataHealth }) {
  const surfaces = Object.keys(d.clicks_by_position).sort((a, b) => (a === "all" ? -1 : b === "all" ? 1 : a.localeCompare(b)));
  const [surface, setSurface] = useState("all");
  const rows = d.clicks_by_position[surface] ?? [];
  const disc = d.discovery_slots;
  return (
    <Panel icon={<MousePointerClick size={14} className="text-primary" />} title="Click-through by position · last 7 days">
      {surfaces.length === 0 ? <p className="text-xs text-text-muted">No feed impressions yet.</p> : (
        <>
          <select value={surface} onChange={(e) => setSurface(e.target.value)}
            className="rounded border-2 border-border bg-bg px-2 py-1 text-xs text-text" aria-label="Feed">
            {surfaces.map((s) => <option key={s} value={s}>{s === "all" ? "All feeds" : s}</option>)}
          </select>
          <Bars label={`Click-through by position, ${surface}`} items={rows.map((p) => ({
            key: String(p.position), value: p.ctr ?? 0, tick: String(p.position + 1),
            tip: `Position ${p.position + 1}: ${pct(p.ctr)} (${p.clicks} of ${p.impressions})`,
          }))} />
          <details className="text-xs">
            <summary className="cursor-pointer text-text-muted">Table</summary>
            <table className="w-full mt-2">
              <thead><tr className="text-text-muted text-left"><th className="py-1">Position</th><th className="text-right">Shown</th><th className="text-right">Clicked</th><th className="text-right">CTR</th></tr></thead>
              <tbody>{rows.map((p) => (
                <tr key={p.position} className="border-t border-border"><td className="py-1">{p.position + 1}</td>
                  <td className="text-right">{p.impressions}</td><td className="text-right">{p.clicks}</td><td className="text-right">{pct(p.ctr)}</td></tr>
              ))}</tbody>
            </table>
          </details>
        </>
      )}
      <div className="grid grid-cols-2 gap-3 pt-1 border-t border-border">
        <Stat label="Discovery slots" value={pct(disc.discovery.ctr)} sub={`${disc.discovery.clicks} of ${disc.discovery.impressions} shown`} />
        <Stat label="Rest of For You" value={pct(disc.other.ctr)} sub={`${disc.other.clicks} of ${disc.other.impressions} shown`} />
      </div>
    </Panel>
  );
}

export default function DataHealthPage() {
  const { token } = useAuthStore();
  const [days, setDays] = useState(14);
  const { data: d, isLoading, isError } = useQuery({
    queryKey: ["data-health", days], queryFn: () => dataHealthApi.get(token!, days), enabled: !!token,
    refetchInterval: 60_000,
  });
  return (
    <div className="flex flex-col pb-24">
      <TopBar title="Data health" back />
      <div className="px-4 pt-4 space-y-4 max-w-3xl w-full mx-auto">
        <div className="flex gap-2" role="group" aria-label="Period">
          {[7, 14, 30].map((n) => (
            <button key={n} onClick={() => setDays(n)} aria-pressed={days === n}
              className={cn("px-3 py-1.5 rounded border-2 text-xs font-bold",
                days === n ? "bg-primary text-on-primary border-primary" : "border-border text-text-secondary")}>
              {n} days
            </button>
          ))}
        </div>
        {isLoading && <p className="text-sm text-text-muted">Loading…</p>}
        {isError && <p className="text-sm text-error">Couldn&apos;t load the report.</p>}
        {d && (
          <>
            <Volume d={d} />
            <Panel icon={<Clock size={14} className="text-primary" />} title="Freshness">
              <div className="grid grid-cols-2 gap-4">
                <Stat label="Last event received" value={ago(d.ingestion.last_received_at)} />
                <Stat label="App events arrive" value={secs(d.ingestion.p50_seconds)}
                  sub={`after they happen (median); 95% within ${secs(d.ingestion.p95_seconds)}, slowest ${secs(d.ingestion.max_seconds)}`} />
                <Stat label="Event features" value={ago(d.features.event_features.computed_at)} sub={`${d.features.event_features.rows.toLocaleString()} events · every 15 min`} />
                <Stat label="People features" value={ago(d.features.user_features.computed_at)} sub={`${d.features.user_features.rows.toLocaleString()} people · nightly`} />
              </div>
            </Panel>
            <Positions d={d} />
            <Panel icon={<Search size={14} className="text-primary" />} title="Searches that found nothing · last 7 days">
              {d.zero_result_searches.length === 0 ? <p className="text-xs text-text-muted">None.</p> : (
                <ul className="text-sm space-y-0.5">
                  {d.zero_result_searches.map((s) => (
                    <li key={s.query} className="flex justify-between gap-3"><span className="text-text truncate">&quot;{s.query}&quot;</span>
                      <span className="text-text-secondary shrink-0">{s.people} {s.people === 1 ? "person" : "people"}</span></li>
                  ))}
                </ul>
              )}
            </Panel>
            <p className="flex items-center gap-1.5 text-[10px] text-text-muted">
              <Sparkles size={11} aria-hidden /> {d.recs_served_7d.toLocaleString()} For You feeds served in 7 days ·
              <Database size={11} aria-hidden /> updated {ago(d.generated_at)}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
