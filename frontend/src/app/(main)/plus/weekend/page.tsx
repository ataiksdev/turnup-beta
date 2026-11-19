"use client";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import Link from "next/link";
import { TopBar } from "@/components/layout/TopBar";
import { apiErrorMessage } from "@/lib/api";
import { plusApi } from "@/lib/marketplace";
import { routes } from "@/lib/routes";
import { useAuthStore } from "@/store/auth";

export default function WeekendPicksPage() {
  const { token, hasHydrated } = useAuthStore();
  const { data, error } = useQuery({ queryKey: ["plus", "weekend"], queryFn: () => plusApi.weekend(token!), enabled: hasHydrated && !!token, retry: false });
  return (
    <div className="pb-24">
      <TopBar back title="Weekend picks" />
      <div className="px-4 py-4 space-y-2">
        {error && (
          <p className="text-sm text-text-muted">{apiErrorMessage(error, "Couldn't load your picks.")}{" "}
            <Link href="/plus" className="text-primary font-bold underline">Turnup+</Link></p>
        )}
        {data && (
          <p className="text-xs text-text-muted">
            {format(new Date(data.weekend_start), "EEE d MMM")} – {format(new Date(data.weekend_end), "EEE d MMM")}
            {data.city ? ` · ${data.city}` : ""}
          </p>
        )}
        {data?.events.length === 0 && <p className="text-sm text-text-muted">Nothing for this weekend yet. Check back Thursday.</p>}
        {data?.events.map((e) => (
          <Link key={e.id} href={routes.event(e.slug)} className="flex gap-3 p-2 rounded border-2 border-border bg-bg-card hover:border-primary">
            <div className="w-16 h-16 rounded bg-bg-elevated overflow-hidden shrink-0">
              {e.cover_image && <img src={e.cover_image} alt="" className="w-full h-full object-cover" />}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-bold text-text truncate">{e.title}</p>
              <p className="text-xs text-text-muted">{format(new Date(e.start_date), "EEE h:mm a")} · {e.venue_name}</p>
              <p className="text-[10px] font-black uppercase text-primary">{e.because}</p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
