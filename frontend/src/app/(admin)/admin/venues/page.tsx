"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { adminMarketApi } from "@/lib/marketplace";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";

const FILTERS = [
  ["To review", { verification: "documents_submitted" }], ["Live", { status: "live" }], ["Paused", { status: "paused" }],
  ["Suspended", { status: "suspended" }], ["Drafts", { status: "draft" }], ["All", {}],
] as const;

export default function AdminVenuesPage() {
  const { token } = useAuthStore();
  const [filter, setFilter] = useState(0);
  const [q, setQ] = useState("");
  const overview = useQuery({ queryKey: ["admin", "market", "overview"], queryFn: () => adminMarketApi.overview(token!), enabled: !!token });
  const list = useQuery({
    queryKey: ["admin", "venues", filter, q], enabled: !!token,
    queryFn: () => adminMarketApi.venues(token!, { ...FILTERS[filter][1], q: q || undefined }),
  });
  const o = overview.data;
  return (
    <div className="pb-24">
      <TopBar title="Venues" />
      <div className="p-4 space-y-4">
        {o && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[["To review", o.venues_to_review], ["Open visits", o.visits_open], ["Open disputes", o.disputes_open],
              ["Late refunds", o.refunds_late], ["Off-platform reports", o.reports_open], ["Chargebacks", o.chargebacks_open],
              ["Unmapped areas", o.unmapped_areas], ["Live venues", o.live_venues]].map(([l, n]) => (
              <div key={l as string} className="p-3 rounded border-2 border-border bg-bg-card">
                <p className="text-[10px] font-black uppercase text-text-muted">{l}</p><p className="text-xl font-black text-text">{n}</p>
              </div>
            ))}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          {FILTERS.map(([label], i) => (
            <button key={label} onClick={() => setFilter(i)}
              className={cn("px-2.5 py-1 rounded border-2 text-xs font-bold", filter === i ? "bg-text text-bg border-border" : "border-border-subtle text-text-secondary")}>{label}</button>
          ))}
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name"
            className="ml-auto h-8 rounded border-2 border-border bg-bg-card px-2 text-sm text-text" />
        </div>
        <div className="space-y-2">
          {list.data?.length === 0 && <p className="text-sm text-text-muted">Nothing here.</p>}
          {list.data?.map((v) => (
            <Link key={v.id} href={`/admin/venues/detail?id=${v.id}`} className="flex items-center gap-3 p-3 rounded border-2 border-border bg-bg-card hover:border-primary">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-black text-text truncate">{v.name}</p>
                <p className="text-xs text-text-muted">{[v.area ?? v.area_other, v.state].filter(Boolean).join(", ")}{v.area_other && !v.area ? " (unmapped area)" : ""}</p>
              </div>
              <span className="text-[10px] font-black uppercase text-text-secondary">{v.status} · {v.verification_status.replace(/_/g, " ")}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
