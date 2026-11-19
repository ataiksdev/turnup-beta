"use client";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import Link from "next/link";
import { agentApi } from "@/lib/marketplace";
import { useAuthStore } from "@/store/auth";

export default function AgentHome() {
  const { token } = useAuthStore();
  const me = useQuery({ queryKey: ["agent", "me"], queryFn: () => agentApi.me(token!), retry: false });
  const visits = useQuery({ queryKey: ["agent", "visits"], queryFn: () => agentApi.visits(token!), enabled: me.isSuccess });
  if (me.isError) return <p className="text-sm text-text-muted">This page is for Turnup agents.</p>;
  const open = visits.data?.filter((v) => ["assigned", "scheduled"].includes(v.status)) ?? [];
  const done = visits.data?.filter((v) => !["assigned", "scheduled"].includes(v.status)) ?? [];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-text">Venue visits</h1>
        {me.data && <p className="text-xs text-text-muted">Your states: {me.data.states.join(", ")}</p>}
      </div>
      {[["To visit", open], ["Done", done]].map(([title, list]) => (
        <section key={title as string} className="space-y-2">
          <h2 className="text-xs font-black uppercase tracking-widest text-text">{title as string}</h2>
          {(list as typeof open).length === 0 && <p className="text-sm text-text-muted">None.</p>}
          {(list as typeof open).map((v) => (
            <Link key={v.id} href={`/agent/visit?id=${v.id}`} className="block p-3 rounded border-2 border-border bg-bg-card hover:border-primary">
              <p className="text-sm font-black text-text">{v.venue.name}</p>
              <p className="text-xs text-text-muted">{v.venue.address}, {[v.venue.area, v.venue.state].filter(Boolean).join(", ")}</p>
              <p className="text-[10px] font-black uppercase text-primary">{v.status}{v.scheduled_for ? ` · ${format(new Date(v.scheduled_for), "EEE d MMM, h:mm a")}` : ""}</p>
            </Link>
          ))}
        </section>
      ))}
    </div>
  );
}
