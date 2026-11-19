"use client";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import Link from "next/link";
import { TopBar } from "@/components/layout/TopBar";
import { plusApi } from "@/lib/marketplace";
import { routes } from "@/lib/routes";
import { useAuthStore } from "@/store/auth";

export default function DealsWalletPage() {
  const { token, hasHydrated } = useAuthStore();
  const { data } = useQuery({ queryKey: ["plus", "deals"], queryFn: () => plusApi.myDeals(token!), enabled: hasHydrated && !!token });
  return (
    <div className="pb-24">
      <TopBar back title="My deals" />
      <div className="px-4 py-4 space-y-2">
        <p className="text-xs text-text-muted">Show the code at the door. Venues and event staff check it with Turnup.</p>
        {data?.length === 0 && <p className="text-sm text-text-muted">No deals yet. Look for Turnup+ deals on venue and event pages.</p>}
        {data?.map((d) => (
          <div key={d.code} className="p-4 rounded border-2 border-border bg-bg-card space-y-1">
            <p className="text-sm font-bold text-text">{d.deal.title}</p>
            {d.where && (
              <Link href={d.where.type === "venue" ? routes.venue(d.where.slug) : routes.event(d.where.id)}
                className="text-xs text-primary font-bold underline">{d.where.name}</Link>
            )}
            <p className="font-mono text-2xl font-black tracking-widest text-text">{d.code}</p>
            <p className="text-[11px] text-text-muted">
              {d.redeemed_at ? `Used ${format(new Date(d.redeemed_at), "d MMM, h:mm a")}`
                : d.deal.valid_to ? `Valid until ${format(new Date(d.deal.valid_to), "d MMM yyyy")}` : "Not used yet"}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
