"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { MessageCircle } from "lucide-react";
import { shareApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { routes } from "@/lib/routes";

/** Own profile: how many people your share links brought to events. Hidden until a link
 *  has been opened. */
export function YourShares() {
  const { token } = useAuthStore();
  const { data } = useQuery({
    queryKey: ["share", "mine"], queryFn: () => shareApi.mine(token!), enabled: !!token, staleTime: 60_000,
  });
  if (!data || data.opens === 0) return null;
  const top = data.events.filter((e) => e.going + e.bought + e.saved > 0).slice(0, 3);
  return (
    <div className="px-4 pb-4">
      <div className="p-3 rounded border-2 border-border bg-bg-card space-y-2">
        <p className="flex items-center gap-2 text-sm font-bold text-text">
          <MessageCircle size={16} className="text-success" aria-hidden />
          {data.people_brought > 0
            ? `You've brought ${data.people_brought} ${data.people_brought === 1 ? "person" : "people"} to events`
            : `Your shared links were opened ${data.opens} time${data.opens === 1 ? "" : "s"}`}
        </p>
        {top.length > 0 && (
          <ul className="space-y-1">
            {top.map((e) => (
              <li key={e.event_id} className="text-xs text-text-muted flex justify-between gap-2">
                <Link href={routes.event(e.slug)} className="truncate hover:text-text">{e.title}</Link>
                <span className="shrink-0">
                  {[e.going + e.bought && `${e.going + e.bought} going`, e.saved && `${e.saved} saved`]
                    .filter(Boolean).join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="text-[10px] text-text-muted">Counted when someone opens your link and goes, buys or saves within a week.</p>
      </div>
    </div>
  );
}
