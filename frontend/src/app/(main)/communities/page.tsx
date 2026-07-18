"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { communitiesApi, type Community } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Search, Users, Lock, Plus, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { displayName } from "@/lib/utils";

function PlatformDots({ links }: { links: Record<string, string> }) {
  const platforms = Object.keys(links).filter((k) => !!links[k]);
  if (!platforms.length) return null;
  const colors: Record<string, string> = {
    whatsapp: "#25D366", instagram: "#E1306C", discord: "#5865F2",
    telegram: "#2AABEE", twitter: "#000000", facebook: "#1877F2",
    tiktok: "#010101", youtube: "#FF0000", website: "#6B7280",
  };
  return (
    <div className="flex items-center gap-1" aria-label="Social platforms">
      {platforms.slice(0, 5).map((p) => (
        <span
          key={p}
          style={{ background: colors[p] ?? "#6B7280" }}
          className="w-2 h-2 rounded-full"
          title={p}
        />
      ))}
    </div>
  );
}

function CommunityCard({ community }: { community: Community }) {
  return (
    <Link
      href={`/communities/${community.slug}`}
      className="flex flex-col gap-3 p-4 rounded border-2 border-border bg-bg-card hover:border-primary transition-all shadow-brutal-sm hover:shadow-brutal active:shadow-none active:translate-x-0.5 active:translate-y-0.5"
    >
      {/* Cover / icon header */}
      <div className="relative h-24 rounded overflow-hidden bg-gradient-to-br from-primary/20 to-bg-elevated">
        {community.cover_image && (
          <img src={community.cover_image} alt="" className="w-full h-full object-cover" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/40 to-transparent" />
        <div className="absolute bottom-2 left-2 flex items-center gap-1.5">
          {community.icon && (
            <span className="text-2xl">{community.icon}</span>
          )}
          {community.is_private && (
            <Lock size={12} className="text-white/80" />
          )}
          {community.is_verified_community && (
            <CheckCircle2 size={12} className="text-primary" fill="white" />
          )}
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-black text-text leading-tight line-clamp-1">{community.name}</h3>
          {community.is_member && (
            <span className="shrink-0 px-1.5 py-0.5 rounded border border-primary/40 bg-primary/10 text-[9px] font-black text-primary uppercase tracking-wide">
              Joined
            </span>
          )}
        </div>

        {community.description && (
          <p className="text-xs text-text-muted line-clamp-2 leading-relaxed">{community.description}</p>
        )}

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span className="flex items-center gap-1">
              <Users size={10} /> {community.member_count.toLocaleString()}
            </span>
            {community.city && (
              <span className="text-text-muted">· {community.city}</span>
            )}
          </div>
          <PlatformDots links={community.social_links as Record<string, string>} />
        </div>
      </div>
    </Link>
  );
}

export default function CommunitiesPage() {
  const { token } = useAuthStore();
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<"all" | "mine">("all");

  const allQuery = useQuery({
    queryKey: ["communities", q],
    queryFn: () => communitiesApi.list({ q: q || undefined }),
  });

  const myQuery = useQuery({
    queryKey: ["communities-my"],
    queryFn: () => communitiesApi.my(token!),
    enabled: !!token && tab === "mine",
  });

  const communities = tab === "mine" ? myQuery.data : allQuery.data;
  const isLoading = tab === "mine" ? myQuery.isLoading : allQuery.isLoading;

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="Communities" />

      <div className="px-4 py-3 space-y-3">
        {/* Tab row + Create button */}
        <div className="flex items-center gap-2">
          <div className="flex flex-1 border-2 border-border rounded overflow-hidden">
            {(["all", "mine"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "flex-1 py-2 text-xs font-black uppercase tracking-widest transition-colors",
                  tab === t ? "bg-primary text-white" : "text-text-muted hover:text-text bg-bg-card",
                  t === "all" && "border-r-2 border-border",
                )}
              >
                {t === "all" ? "Discover" : "My Communities"}
              </button>
            ))}
          </div>
          {token && (
            <Link
              href="/communities/new"
              className="flex items-center justify-center w-10 h-10 rounded border-2 border-primary bg-primary/10 text-primary hover:bg-primary hover:text-white transition-colors shadow-brutal-sm"
              aria-label="Create community"
            >
              <Plus size={18} />
            </Link>
          )}
        </div>

        {/* Search (only on discover tab) */}
        {tab === "all" && (
          <Input
            placeholder="Search communities…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            icon={<Search size={16} />}
          />
        )}
      </div>

      {/* Grid */}
      <div className="px-4">
        {isLoading ? (
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="rounded border-2 border-border bg-bg-card overflow-hidden">
                <div className="skeleton-shimmer bg-bg-elevated h-24 w-full" />
                <div className="p-3 space-y-2">
                  <div className="skeleton-shimmer h-4 w-3/4 rounded bg-bg-elevated" />
                  <div className="skeleton-shimmer h-3 w-full rounded bg-bg-elevated" />
                  <div className="skeleton-shimmer h-3 w-1/2 rounded bg-bg-elevated" />
                </div>
              </div>
            ))}
          </div>
        ) : !communities?.length ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
            <Users size={40} className="text-border-strong" />
            <p className="text-sm font-black text-text-secondary uppercase tracking-wide">
              {tab === "mine" ? "You haven't joined any communities yet" : "No communities found"}
            </p>
            {tab === "mine" && token && (
              <Link href="/communities" onClick={() => setTab("all")} className="text-xs text-primary font-bold">
                Discover communities →
              </Link>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {communities.map((c) => (
              <CommunityCard key={c.id} community={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
