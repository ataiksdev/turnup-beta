"use client";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage } from "@/lib/api";
import { downloadWithAuth, plusApi } from "@/lib/marketplace";
import { useAuthStore } from "@/store/auth";

function defaultYear() {
  const now = new Date();
  return now.getMonth() === 11 ? now.getFullYear() : now.getFullYear() - 1;
}

export default function WrappedPage() {
  const { token, hasHydrated } = useAuthStore();
  const [year, setYear] = useState(defaultYear());
  const [error, setError] = useState("");
  const { data, error: loadError } = useQuery({
    queryKey: ["wrapped", year], queryFn: () => plusApi.wrapped(token!, year), enabled: hasHydrated && !!token, retry: false,
  });
  return (
    <div className="pb-24">
      <TopBar back title={`Wrapped ${year}`} />
      <div className="px-4 py-4 space-y-4">
        <select aria-label="Year" value={year} onChange={(e) => setYear(Number(e.target.value))}
          className="h-9 rounded border-2 border-border bg-bg-card px-2 text-sm font-bold text-text">
          {[0, 1, 2].map((i) => defaultYear() - i).map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        {loadError && <p className="text-sm text-text-muted">{apiErrorMessage(loadError, "Couldn't load your Wrapped.")}</p>}
        {data && (
          <>
            <section className="p-5 rounded border-2 border-border bg-gradient-to-br from-primary/30 to-bg-card space-y-3">
              <p className="text-5xl font-black text-text">{data.events_attended}</p>
              <p className="text-sm font-bold text-text-secondary">events in {data.year} · {data.venues_count} venues · {data.cities_count} cities</p>
              {data.full ? (
                <div className="space-y-3 text-sm text-text">
                  {data.busiest_month && <p>Busiest month: <b>{data.busiest_month}</b></p>}
                  {!!data.top_venues?.length && <div><p className="text-xs font-black uppercase">Top venues</p>
                    {data.top_venues.map((v) => <p key={v.name}>{v.name} ({v.visits})</p>)}</div>}
                  {!!data.top_organizers?.length && <div><p className="text-xs font-black uppercase">Top organizers</p>
                    {data.top_organizers.map((v) => <p key={v.name}>{v.name} ({v.events})</p>)}</div>}
                  {!!data.went_with?.length && <div><p className="text-xs font-black uppercase">Went out most with</p>
                    {data.went_with.map((v) => <p key={v.username}>{v.name} ({v.events})</p>)}</div>}
                </div>
              ) : (
                <p className="text-sm text-text-secondary">See your top venues, organizers and friends with <Link href="/plus" className="text-primary font-bold underline">Turnup+</Link>.</p>
              )}
            </section>
            <Button variant="secondary" onClick={() => downloadWithAuth(token!, plusApi.wrappedImageUrl(year), `turnup-wrapped-${year}.png`)
              .catch((e) => setError(apiErrorMessage(e, "Couldn't make the image.")))}>
              <Download size={14} aria-hidden /> Save image to share
            </Button>
            {error && <p className="text-xs text-error">{error}</p>}
          </>
        )}
      </div>
    </div>
  );
}
