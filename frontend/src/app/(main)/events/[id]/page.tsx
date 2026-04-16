"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { eventsApi, socialApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { formatEventDate, formatPrice, parseTags, timeAgo } from "@/lib/utils";
import {
  Bookmark, BookmarkCheck, Calendar, ExternalLink,
  MapPin, Share2, Tag, Users, MessageCircle, CheckCircle2
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { useParams } from "next/navigation";

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token, user } = useAuthStore();
  const qc = useQueryClient();

  const { data: event, isLoading } = useQuery({
    queryKey: ["event", id],
    queryFn: () => eventsApi.get(id, token ?? undefined),
  });

  const { data: comments } = useQuery({
    queryKey: ["comments", id],
    queryFn: () => socialApi.comments(id),
    enabled: !!id,
  });

  const [comment, setComment] = useState("");
  const [saved, setSaved] = useState(event?.is_saved ?? false);
  const [attendance, setAttendance] = useState(event?.attendance_status ?? null);

  const attendMutation = useMutation({
    mutationFn: (status: "going" | "interested") =>
      token ? eventsApi.attend(token, id, status) : Promise.reject(),
    onSuccess: (_, status) => {
      setAttendance(status);
      qc.invalidateQueries({ queryKey: ["event", id] });
    },
  });

  const removeAttendMutation = useMutation({
    mutationFn: () => token ? eventsApi.removeAttendance(token, id) : Promise.reject(),
    onSuccess: () => {
      setAttendance(null);
      qc.invalidateQueries({ queryKey: ["event", id] });
    },
  });

  const saveMutation = useMutation({
    mutationFn: () => token ? eventsApi.save(token, id) : Promise.reject(),
    onSuccess: (res) => setSaved(res.saved),
  });

  const commentMutation = useMutation({
    mutationFn: () =>
      token && comment.trim()
        ? socialApi.addComment(token, id, comment.trim())
        : Promise.reject(),
    onSuccess: () => {
      setComment("");
      qc.invalidateQueries({ queryKey: ["comments", id] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!event) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-3">
        <span className="text-5xl">😕</span>
        <p className="text-text-secondary">Event not found</p>
      </div>
    );
  }

  const tags = parseTags(event.tags);
  const isGoing = attendance === "going";
  const isInterested = attendance === "interested";

  return (
    <div className="flex flex-col pb-8">
      {/* Header image */}
      <div className="relative h-72 w-full">
        {event.cover_image ? (
          <Image src={event.cover_image} alt={event.title} fill className="object-cover" priority sizes="100vw" />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-primary/20 to-bg" />
        )}
        <div className="absolute inset-0 bg-hero-overlay" />
        <TopBar back transparent className="absolute top-0 inset-x-0" actions={
          <button onClick={() => saveMutation.mutate()}
            className="p-2 rounded-xl bg-bg/60 backdrop-blur-sm hover:bg-bg/80 transition-colors">
            {saved
              ? <BookmarkCheck size={18} className="text-primary" />
              : <Bookmark size={18} className="text-white" />}
          </button>
        } />

        {event.is_trending && (
          <div className="absolute top-16 left-4">
            <span className="px-2.5 py-1 rounded-full bg-primary text-white text-xs font-bold">
              🔥 Trending
            </span>
          </div>
        )}
      </div>

      <div className="px-4 space-y-5 mt-4">
        {/* Category & title */}
        {event.category && (
          <span className="text-xs font-medium text-primary uppercase tracking-widest">
            {event.category.icon} {event.category.name}
          </span>
        )}
        <h1 className="text-2xl font-black text-text leading-tight">{event.title}</h1>

        {/* Meta */}
        <div className="space-y-2.5">
          <div className="flex items-center gap-2.5 text-sm text-text-secondary">
            <Calendar size={16} className="text-primary shrink-0" />
            {formatEventDate(event.start_date)}
          </div>
          <div className="flex items-center gap-2.5 text-sm text-text-secondary">
            <MapPin size={16} className="text-primary shrink-0" />
            <span>{event.venue_name}, {event.address}, {event.city}</span>
          </div>
          <div className="flex items-center gap-2.5 text-sm text-text-secondary">
            <Users size={16} className="text-primary shrink-0" />
            <span>
              <strong className="text-text">{event.attendees_count.toLocaleString()}</strong> going ·{" "}
              <strong className="text-text">{event.interested_count.toLocaleString()}</strong> interested
            </span>
          </div>
        </div>

        {/* Price */}
        <div className="flex items-center justify-between p-4 rounded-2xl bg-bg-card border border-border">
          <div>
            <p className="text-xs text-text-muted">Admission</p>
            <p className={`text-xl font-black ${event.is_free ? "text-success" : "text-primary"}`}>
              {formatPrice(event.is_free, event.price_min, event.price_max)}
            </p>
          </div>
          {event.ticket_url && (
            <a href={event.ticket_url} target="_blank" rel="noopener noreferrer">
              <Button size="sm" variant="outline">
                Get Tickets <ExternalLink size={12} />
              </Button>
            </a>
          )}
        </div>

        {/* RSVP buttons */}
        {user && (
          <div className="flex gap-2">
            <Button
              fullWidth
              variant={isGoing ? "primary" : "secondary"}
              loading={attendMutation.isPending}
              onClick={() => isGoing ? removeAttendMutation.mutate() : attendMutation.mutate("going")}
            >
              <CheckCircle2 size={16} />
              {isGoing ? "Going ✓" : "I'm Going"}
            </Button>
            <Button
              variant={isInterested ? "outline" : "secondary"}
              loading={attendMutation.isPending}
              onClick={() => isInterested ? removeAttendMutation.mutate() : attendMutation.mutate("interested")}
            >
              {isInterested ? "Interested ✓" : "Interested"}
            </Button>
          </div>
        )}

        {/* Host */}
        <Link href={`/profile/${event.host.username}`}
          className="flex items-center gap-3 p-4 rounded-2xl bg-bg-card border border-border hover:border-border-strong transition-colors">
          <Avatar src={event.host.avatar_url} name={event.host.full_name} size="md" verified={event.host.is_verified} />
          <div className="flex-1 min-w-0">
            <p className="text-xs text-text-muted">Hosted by</p>
            <p className="text-sm font-semibold text-text">{event.host.full_name}</p>
            <p className="text-xs text-text-muted">@{event.host.username}</p>
          </div>
          <span className="text-xs text-primary">View profile →</span>
        </Link>

        {/* Description */}
        <div className="space-y-2">
          <h2 className="text-base font-bold text-text">About</h2>
          <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">{event.description}</p>
        </div>

        {/* Tags */}
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <Badge key={tag} variant="default">
                <Tag size={10} /> #{tag}
              </Badge>
            ))}
          </div>
        )}

        {/* Map placeholder */}
        {event.latitude && event.longitude && (
          <div className="rounded-2xl overflow-hidden border border-border h-40 bg-bg-card flex items-center justify-center">
            <div className="text-center space-y-1">
              <MapPin size={24} className="text-primary mx-auto" />
              <p className="text-xs text-text-muted">{event.venue_name}</p>
              <p className="text-xs text-text-muted">{event.city}</p>
            </div>
          </div>
        )}

        {/* Comments */}
        <div className="space-y-3">
          <h2 className="text-base font-bold text-text flex items-center gap-2">
            <MessageCircle size={18} className="text-primary" />
            Comments {comments && `(${comments.length})`}
          </h2>

          {user && (
            <div className="flex gap-2">
              <Avatar src={user.avatar_url} name={user.full_name} size="sm" />
              <div className="flex-1 flex gap-2">
                <input
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Add a comment..."
                  className="flex-1 bg-bg-card border border-border rounded-2xl px-3 py-2 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
                  onKeyDown={(e) => e.key === "Enter" && commentMutation.mutate()}
                />
                <Button size="sm" onClick={() => commentMutation.mutate()} loading={commentMutation.isPending}>
                  Post
                </Button>
              </div>
            </div>
          )}

          {comments?.map((c) => (
            <div key={c.id} className="flex gap-2.5">
              <Avatar src={c.user.avatar_url} name={c.user.full_name} size="sm" />
              <div className="flex-1 bg-bg-card rounded-2xl px-3 py-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-semibold text-text">@{c.user.username}</span>
                  <span className="text-[10px] text-text-muted">{timeAgo(c.created_at)}</span>
                </div>
                <p className="text-sm text-text-secondary">{c.content}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
