"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { socialApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { timeAgo } from "@/lib/utils";
import Link from "next/link";
import { Bell, Check, UserPlus, PartyPopper, MessageCircle, Clock, Megaphone, Mail, Eye, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { useState } from "react";

type ActivityTab = "feed" | "notifications";

export default function ActivityPage() {
  const { token, user } = useAuthStore();
  const qc = useQueryClient();
  const [tab, setTab] = useState<ActivityTab>("feed");

  const { data: feed, isLoading: feedLoading } = useQuery({
    queryKey: ["feed"],
    queryFn: () => token ? socialApi.feed(token) : Promise.resolve([]),
    enabled: !!token && tab === "feed",
  });

  const { data: notifications, isLoading: notifsLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => token ? socialApi.notifications(token) : Promise.resolve([]),
    enabled: !!token && tab === "notifications",
  });

  const markReadMutation = useMutation({
    mutationFn: () => token ? socialApi.markAllRead(token) : Promise.reject(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unreadCount = notifications?.filter((n) => !n.is_read).length ?? 0;

  if (!user || !token) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4 px-8 text-center">
        <Zap size={48} className="text-primary" aria-hidden />
        <h2 className="text-xl font-black text-text">Join the action</h2>
        <p className="text-sm text-text-secondary">Log in to see activity from people you follow.</p>
        <Link href="/login"><Button fullWidth>Log In</Button></Link>
        <Link href="/signup" className="text-sm text-primary">Create an account →</Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="Activity" />

      {/* Tabs */}
      <div className="flex border-b border-border px-4">
        {(["feed", "notifications"] as ActivityTab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "flex-1 py-3 text-sm font-medium capitalize transition-colors relative",
              tab === t
                ? "text-primary border-b-2 border-primary"
                : "text-text-muted hover:text-text-secondary",
            )}
          >
            {t}
            {t === "notifications" && unreadCount > 0 && (
              <span className="absolute top-2 right-1/4 w-4 h-4 rounded-full bg-primary text-white text-[9px] flex items-center justify-center font-bold">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Feed */}
      {tab === "feed" && (
        <div className="divide-y divide-border">
          {feedLoading ? (
            <div className="flex justify-center py-10">
              <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent animate-spin" />
            </div>
          ) : feed && feed.length > 0 ? (
            feed.map((item, i) => (
              <div key={i} className="flex items-start gap-3 px-4 py-3.5">
                <Link href={`/profile/${item.actor.username}`}>
                  <Avatar src={item.actor.avatar_url} name={item.actor.full_name} size="md" />
                </Link>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-text-secondary leading-snug">
                    <Link href={`/profile/${item.actor.username}`}
                      className="font-semibold text-text hover:text-primary">
                      @{item.actor.username}
                    </Link>
                    {" "}
                    {item.type === "attendance" && (
                      <>is <span className="text-primary font-medium">{item.status}</span> {" "}
                        <Link href={`/events/${item.event?.slug}`} className="font-semibold text-text hover:text-primary">
                          {item.event?.title}
                        </Link>
                      </>
                    )}
                    {item.type === "follow" && (
                      <>started following {" "}
                        <Link href={`/profile/${item.target_user?.username}`}
                          className="font-semibold text-text hover:text-primary">
                          @{item.target_user?.username}
                        </Link>
                      </>
                    )}
                  </p>
                  <p className="text-[11px] text-text-muted mt-0.5">{timeAgo(item.created_at)}</p>
                </div>
                {item.type === "attendance" && item.event?.cover_image && (
                  <Link href={`/events/${item.event.slug}`}>
                    <div className="w-12 h-12 rounded-xl overflow-hidden shrink-0 bg-bg-elevated">
                      <img src={item.event.cover_image} alt="" className="w-full h-full object-cover" />
                    </div>
                  </Link>
                )}
              </div>
            ))
          ) : (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-center px-8">
              <Eye size={40} className="text-border-strong" aria-hidden />
              <p className="text-text-secondary font-medium">Nothing here yet</p>
              <p className="text-sm text-text-muted">Follow people to see their activity</p>
            </div>
          )}
        </div>
      )}

      {/* Notifications */}
      {tab === "notifications" && (
        <div>
          {unreadCount > 0 && (
            <div className="px-4 py-2 flex justify-end">
              <button
                onClick={() => markReadMutation.mutate()}
                className="flex items-center gap-1.5 text-xs text-primary font-medium"
              >
                <Check size={12} /> Mark all read
              </button>
            </div>
          )}

          <div className="divide-y divide-border">
            {notifsLoading ? (
              <div className="flex justify-center py-10">
                <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent animate-spin" />
              </div>
            ) : notifications && notifications.length > 0 ? (
              notifications.map((n) => (
                <div key={n.id} className={cn(
                  "flex items-start gap-3 px-4 py-3.5",
                  !n.is_read && "bg-primary/5",
                )}>
                  <div className="w-9 h-9 rounded-full bg-bg-card border border-border flex items-center justify-center shrink-0 text-text-muted">
                    {n.type === "follow"         && <UserPlus    size={16} aria-hidden />}
                    {n.type === "going"          && <PartyPopper size={16} aria-hidden />}
                    {n.type === "comment"        && <MessageCircle size={16} aria-hidden />}
                    {n.type === "event_reminder" && <Clock       size={16} aria-hidden />}
                    {n.type === "event_update"   && <Megaphone   size={16} aria-hidden />}
                    {n.type === "event_invite"   && <Mail        size={16} aria-hidden />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-text">{n.title}</p>
                    {n.body && <p className="text-xs text-text-muted mt-0.5">{n.body}</p>}
                    <p className="text-[11px] text-text-muted mt-1">{timeAgo(n.created_at)}</p>
                  </div>
                  {!n.is_read && (
                    <div className="w-2 h-2 rounded-full bg-primary mt-1 shrink-0" />
                  )}
                </div>
              ))
            ) : (
              <div className="flex flex-col items-center justify-center py-20 gap-3 text-center px-8">
                <Bell size={40} className="text-border-strong" />
                <p className="text-text-secondary font-medium">All caught up!</p>
                <p className="text-sm text-text-muted">No notifications yet</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
