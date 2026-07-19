"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { communitiesApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/Avatar";
import { EventCard } from "@/components/events/EventCard";
import { formatEventDate, formatPrice, displayName } from "@/lib/utils";
import {
  Users, Lock, CheckCircle2, Settings, Link2, Copy, Check,
  ExternalLink, Calendar, Ticket,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { cn, copyToClipboard } from "@/lib/utils";

// ── Platform brand icons ───────────────────────────────────────────────────────

const PLATFORM_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  whatsapp:  { label: "WhatsApp",  color: "#fff", bg: "#25D366" },
  instagram: { label: "Instagram", color: "#fff", bg: "#E1306C" },
  discord:   { label: "Discord",   color: "#fff", bg: "#5865F2" },
  telegram:  { label: "Telegram",  color: "#fff", bg: "#2AABEE" },
  twitter:   { label: "Twitter/X", color: "#fff", bg: "#000000" },
  facebook:  { label: "Facebook",  color: "#fff", bg: "#1877F2" },
  tiktok:    { label: "TikTok",    color: "#fff", bg: "#010101" },
  youtube:   { label: "YouTube",   color: "#fff", bg: "#FF0000" },
  website:   { label: "Website",   color: "#fff", bg: "#6B7280" },
};

function PlatformButtons({ links }: { links: Record<string, string | null | undefined> }) {
  const entries = Object.entries(links).filter(([, v]) => !!v) as [string, string][];
  if (!entries.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([platform, url]) => {
        const cfg = PLATFORM_CONFIG[platform] ?? { label: platform, color: "#fff", bg: "#6B7280" };
        return (
          <a
            key={platform}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ background: cfg.bg, color: cfg.color }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition-opacity hover:opacity-80"
          >
            <ExternalLink size={11} />
            {cfg.label}
          </a>
        );
      })}
    </div>
  );
}

type Tab = "events" | "members" | "about";

export function CommunityDetailClient() {
  const { slug } = useParams<{ slug: string }>();
  const { token, user } = useAuthStore();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("events");
  const [copied, setCopied] = useState(false);
  const [actionError, setActionError] = useState("");

  const { data: community, isLoading } = useQuery({
    queryKey: ["community", slug],
    queryFn: () => communitiesApi.get(slug, token ?? undefined),
  });

  const eventsQuery = useQuery({
    queryKey: ["community-events", slug],
    queryFn: () => communitiesApi.events(slug),
    enabled: tab === "events",
  });

  const membersQuery = useQuery({
    queryKey: ["community-members", slug],
    queryFn: () => communitiesApi.members(slug),
    enabled: tab === "members",
  });

  const joinMutation = useMutation({
    mutationFn: () => communitiesApi.join(token!, slug),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["community", slug] }),
    onError: (e: any) => { setActionError(e.message ?? "Failed to join"); setTimeout(() => setActionError(""), 3000); },
  });

  const leaveMutation = useMutation({
    mutationFn: () => communitiesApi.leave(token!, slug),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["community", slug] }),
    onError: (e: any) => { setActionError(e.message ?? "Failed to leave"); setTimeout(() => setActionError(""), 3000); },
  });

  function copyInviteLink() {
    if (!community?.invite_token) return;
    const url = `${window.location.origin}/communities/join/${community.invite_token}`;
    copyToClipboard(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (isLoading) {
    return (
      <div className="flex flex-col">
        <TopBar back title="Community" />
        <div className="h-48 skeleton-shimmer bg-bg-elevated" />
        <div className="px-4 py-4 space-y-3">
          <div className="skeleton-shimmer h-6 w-48 rounded bg-bg-elevated" />
          <div className="skeleton-shimmer h-4 w-full rounded bg-bg-elevated" />
          <div className="skeleton-shimmer h-4 w-3/4 rounded bg-bg-elevated" />
        </div>
      </div>
    );
  }

  if (!community) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-3">
        <Users size={40} className="text-border-strong" />
        <p className="text-sm font-black text-text-secondary uppercase tracking-wide">Community not found</p>
        <Link href="/communities" className="text-primary text-sm font-medium">← Back</Link>
      </div>
    );
  }

  const isAdmin = community.member_role === "admin";
  const isMod = community.member_role === "moderator";
  const isPrivateAndNotMember = community.is_private && !community.is_member;
  const socialLinksObj = community.social_links as Record<string, string>;
  const hasSocialLinks = Object.values(socialLinksObj).some(Boolean);

  return (
    <div className="flex flex-col pb-4">
      <TopBar
        back
        title={community.name}
        actions={
          isAdmin && (
            <Link href={`/communities/${slug}/settings`} className="p-2 rounded hover:bg-bg-elevated transition-colors">
              <Settings size={18} className="text-text-secondary" />
            </Link>
          )
        }
      />

      {/* Hero */}
      <div className="relative h-44 bg-gradient-to-br from-primary/30 to-bg-elevated">
        {community.cover_image && (
          <img src={community.cover_image} alt="" className="w-full h-full object-cover" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
        <div className="absolute bottom-3 left-4 flex items-center gap-2">
          {community.icon && <span className="text-3xl">{community.icon}</span>}
          <div>
            <div className="flex items-center gap-1.5">
              <h1 className="text-lg font-black text-white leading-tight">{community.name}</h1>
              {community.is_verified_community && (
                <CheckCircle2 size={14} className="text-primary fill-white" />
              )}
              {community.is_private && (
                <Lock size={12} className="text-white/70" />
              )}
            </div>
            <p className="text-xs text-white/70">
              {community.member_count.toLocaleString()} member{community.member_count !== 1 ? "s" : ""}
              {community.city && ` · ${community.city}`}
            </p>
          </div>
        </div>
      </div>

      {/* CTA row */}
      <div className="px-4 py-3 flex items-center gap-2">
        {token ? (
          community.is_member ? (
            <Button
              variant="secondary"
              size="sm"
              loading={leaveMutation.isPending}
              onClick={() => leaveMutation.mutate()}
            >
              <Check size={14} /> Joined
            </Button>
          ) : community.is_private ? (
            <span className="text-xs text-text-muted flex items-center gap-1">
              <Lock size={12} /> Private — join via invite link
            </span>
          ) : (
            <Button size="sm" loading={joinMutation.isPending} onClick={() => joinMutation.mutate()}>
              <Users size={14} /> Join Community
            </Button>
          )
        ) : (
          <Link href="/login">
            <Button size="sm"><Users size={14} /> Join to participate</Button>
          </Link>
        )}

        {isAdmin && community.is_private && community.invite_token && (
          <button
            onClick={copyInviteLink}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded border-2 border-border bg-bg-card text-xs font-bold text-text-secondary hover:border-primary hover:text-primary transition-colors"
          >
            {copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
            {copied ? "Copied!" : "Copy invite link"}
          </button>
        )}

        {actionError && <p className="text-xs text-error">{actionError}</p>}
      </div>

      {/* Private gate */}
      {isPrivateAndNotMember ? (
        <div className="mx-4 mt-4 p-6 rounded border-2 border-border bg-bg-card flex flex-col items-center gap-3 text-center">
          <Lock size={32} className="text-text-muted" />
          <p className="text-sm font-black text-text uppercase tracking-wide">Private Community</p>
          <p className="text-xs text-text-muted">You need an invite link to access this community.</p>
        </div>
      ) : (
        <>
          {/* Social link buttons */}
          {hasSocialLinks && (
            <div className="px-4 pb-3">
              <PlatformButtons links={socialLinksObj} />
            </div>
          )}

          {/* Tabs */}
          <div className="flex border-y-2 border-border mx-4 mb-3 rounded overflow-hidden">
            {(["events", "members", "about"] as Tab[]).map((t, i, arr) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "flex-1 py-2.5 text-[10px] font-black uppercase tracking-widest transition-colors",
                  i < arr.length - 1 && "border-r-2 border-border",
                  tab === t ? "bg-primary text-white" : "text-text-muted hover:text-text bg-bg-card",
                )}
              >
                {t === "events" ? `Events (${community.event_count})` : t === "members" ? `Members (${community.member_count})` : "About"}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="px-4">
            {/* Events tab */}
            {tab === "events" && (
              eventsQuery.isLoading ? (
                <div className="grid grid-cols-2 gap-3">
                  {[1,2,3,4].map((i) => (
                    <div key={i} className="rounded border-2 border-border bg-bg-card overflow-hidden">
                      <div className="skeleton-shimmer h-36 w-full bg-bg-elevated" />
                      <div className="p-2 space-y-1.5">
                        <div className="skeleton-shimmer h-3 w-3/4 rounded bg-bg-elevated" />
                        <div className="skeleton-shimmer h-3 w-1/2 rounded bg-bg-elevated" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : eventsQuery.data?.length ? (
                <div className="grid grid-cols-2 gap-3">
                  {eventsQuery.data.map((e: any) => (
                    <Link key={e.id} href={`/events/${e.slug}`}
                      className="rounded border-2 border-border bg-bg-card overflow-hidden hover:border-primary transition-colors">
                      <div className="relative h-28 bg-bg-elevated">
                        {e.cover_image && <img src={e.cover_image} alt="" className="w-full h-full object-cover" />}
                        {e.is_free && (
                          <span className="absolute top-1.5 left-1.5 px-1.5 py-0.5 bg-success text-white text-[9px] font-black rounded uppercase">Free</span>
                        )}
                      </div>
                      <div className="p-2.5 space-y-1">
                        <p className="text-xs font-bold text-text line-clamp-2 leading-snug">{e.title}</p>
                        <p className="text-[10px] text-text-muted flex items-center gap-1">
                          <Calendar size={9} />
                          {formatEventDate(e.start_date)}
                        </p>
                        <p className="text-[10px] font-bold text-primary">
                          {formatPrice(e.is_free, e.price_min, e.price_max)}
                        </p>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center py-16 gap-3 text-center">
                  <Ticket size={36} className="text-border-strong" />
                  <p className="text-sm font-black text-text-secondary uppercase tracking-wide">No events shared yet</p>
                  {community.is_member && (
                    <p className="text-xs text-text-muted">Share an event from its detail page to add it here</p>
                  )}
                </div>
              )
            )}

            {/* Members tab */}
            {tab === "members" && (
              membersQuery.isLoading ? (
                <div className="space-y-3">
                  {[1,2,3].map((i) => (
                    <div key={i} className="flex items-center gap-3">
                      <div className="skeleton-shimmer w-10 h-10 rounded-full bg-bg-elevated" />
                      <div className="flex-1 space-y-1">
                        <div className="skeleton-shimmer h-4 w-32 rounded bg-bg-elevated" />
                        <div className="skeleton-shimmer h-3 w-20 rounded bg-bg-elevated" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-2">
                  {membersQuery.data?.map((m: any) => (
                    <Link
                      key={m.user_id}
                      href={`/profile/${m.username}`}
                      className="flex items-center gap-3 p-3 rounded border-2 border-border bg-bg-card hover:border-primary transition-colors"
                    >
                      <Avatar src={m.avatar_url} name={m.full_name ?? m.username} size="sm" verified={m.is_verified} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-text">{m.full_name}</p>
                        <p className="text-xs text-text-muted">@{m.username}</p>
                      </div>
                      {m.role !== "member" && (
                        <span className={cn(
                          "text-[9px] font-black uppercase tracking-wide px-1.5 py-0.5 rounded border",
                          m.role === "admin" ? "text-primary border-primary/40 bg-primary/10" : "text-text-muted border-border"
                        )}>
                          {m.role}
                        </span>
                      )}
                    </Link>
                  ))}
                </div>
              )
            )}

            {/* About tab */}
            {tab === "about" && (
              <div className="space-y-5">
                {community.description && (
                  <div>
                    <p className="text-xs font-black text-text-muted uppercase tracking-widest mb-2">About</p>
                    <p className="text-sm text-text-secondary leading-relaxed">{community.description}</p>
                  </div>
                )}

                {community.category && (
                  <div>
                    <p className="text-xs font-black text-text-muted uppercase tracking-widest mb-2">Category</p>
                    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border-2 border-border bg-bg-card text-sm font-bold text-text">
                      {community.category.icon} {community.category.name}
                    </span>
                  </div>
                )}

                <div>
                  <p className="text-xs font-black text-text-muted uppercase tracking-widest mb-2">Created by</p>
                  <Link
                    href={`/profile/${community.creator.username}`}
                    className="flex items-center gap-3 p-3 rounded border-2 border-border bg-bg-card hover:border-primary transition-colors"
                  >
                    <Avatar
                      src={community.creator.avatar_url}
                      name={community.creator.full_name}
                      size="sm"
                      verified={community.creator.is_verified}
                    />
                    <div>
                      <p className="text-sm font-semibold text-text">{community.creator.full_name}</p>
                      <p className="text-xs text-text-muted">@{community.creator.username}</p>
                    </div>
                  </Link>
                </div>

                {hasSocialLinks && (
                  <div>
                    <p className="text-xs font-black text-text-muted uppercase tracking-widest mb-2">Links & chat portals</p>
                    <PlatformButtons links={socialLinksObj} />
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
