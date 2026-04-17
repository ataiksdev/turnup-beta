"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { eventsApi, socialApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { ShareButton } from "@/components/ui/ShareButton";
import { EventDetailSkeleton } from "@/components/ui/Skeleton";
import { formatEventDate, formatPrice, parseTags, timeAgo } from "@/lib/utils";
import {
  Bookmark, BookmarkCheck, Calendar, ExternalLink,
  MapPin, Tag, Users, MessageCircle, CheckCircle2,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export function EventDetailClient({ id }: { id: string }) {
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

  const [comment, setComment]   = useState("");
  const [saved, setSaved]       = useState(event?.is_saved ?? false);
  const [attendance, setAttend] = useState(event?.attendance_status ?? null);

  const attendMutation = useMutation({
    mutationFn: (status: "going" | "interested") =>
      token ? eventsApi.attend(token, id, status) : Promise.reject(),
    onSuccess: (_, status) => {
      setAttend(status);
      qc.invalidateQueries({ queryKey: ["event", id] });
    },
  });

  const removeAttendMutation = useMutation({
    mutationFn: () => token ? eventsApi.removeAttendance(token, id) : Promise.reject(),
    onSuccess: () => {
      setAttend(null);
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

  if (isLoading) return <EventDetailSkeleton />;

  if (!event) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-3">
        <span className="text-5xl" aria-hidden>😕</span>
        <p className="text-text-secondary">Event not found</p>
        <Link href="/" className="text-primary text-sm font-medium">← Back to Discover</Link>
      </div>
    );
  }

  const tags    = parseTags(event.tags);
  const isGoing = attendance === "going";
  const isInterested = attendance === "interested";
  const shareUrl = `${SITE}/events/${id}`;

  return (
    <article className="flex flex-col pb-8">
      {/* Hero image */}
      <div className="relative h-72 w-full">
        {event.cover_image ? (
          <Image
            src={event.cover_image}
            alt={event.title}
            fill
            className="object-cover"
            priority
            sizes="100vw"
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-primary/20 to-bg" aria-hidden />
        )}
        <div className="absolute inset-0 bg-hero-overlay" aria-hidden />

        <TopBar
          back
          transparent
          className="absolute top-0 inset-x-0"
          actions={
            <div className="flex items-center gap-1">
              <ShareButton
                title={event.title}
                text={`Check out ${event.title} on Turnup!`}
                url={shareUrl}
                className="bg-bg/60 backdrop-blur-sm hover:bg-bg/80"
                iconClassName="text-white"
              />
              <button
                onClick={() => saveMutation.mutate()}
                aria-label={saved ? "Remove from saved" : "Save event"}
                aria-pressed={saved}
                className="p-2 rounded-xl bg-bg/60 backdrop-blur-sm hover:bg-bg/80 transition-colors"
              >
                {saved
                  ? <BookmarkCheck size={18} className="text-primary" aria-hidden />
                  : <Bookmark size={18} className="text-white" aria-hidden />}
              </button>
            </div>
          }
        />

        {event.is_trending && (
          <div className="absolute top-16 left-4">
            <span className="px-2.5 py-1 rounded-full bg-primary text-white text-xs font-bold">
              🔥 Trending
            </span>
          </div>
        )}
      </div>

      <div className="px-4 space-y-5 mt-4">
        {/* Category */}
        {event.category && (
          <p className="text-xs font-medium text-primary uppercase tracking-widest">
            <span aria-hidden>{event.category.icon}</span>{" "}
            <span>{event.category.name}</span>
          </p>
        )}

        <h1 className="text-2xl font-black text-text leading-tight">{event.title}</h1>

        {/* Meta */}
        <dl className="space-y-2.5">
          <div className="flex items-center gap-2.5 text-sm text-text-secondary">
            <Calendar size={16} className="text-primary shrink-0" aria-hidden />
            <dt className="sr-only">Date</dt>
            <dd>{formatEventDate(event.start_date)}</dd>
          </div>
          <div className="flex items-center gap-2.5 text-sm text-text-secondary">
            <MapPin size={16} className="text-primary shrink-0" aria-hidden />
            <dt className="sr-only">Location</dt>
            <dd>{event.venue_name}, {event.address}, {event.city}</dd>
          </div>
          <div className="flex items-center gap-2.5 text-sm text-text-secondary">
            <Users size={16} className="text-primary shrink-0" aria-hidden />
            <dt className="sr-only">Attendance</dt>
            <dd>
              <strong className="text-text">{event.attendees_count.toLocaleString()}</strong> going ·{" "}
              <strong className="text-text">{event.interested_count.toLocaleString()}</strong> interested
            </dd>
          </div>
        </dl>

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
                Get Tickets <ExternalLink size={12} aria-hidden />
              </Button>
            </a>
          )}
        </div>

        {/* RSVP */}
        {user && (
          <div className="flex gap-2" role="group" aria-label="RSVP options">
            <Button
              fullWidth
              variant={isGoing ? "primary" : "secondary"}
              loading={attendMutation.isPending}
              aria-pressed={isGoing}
              onClick={() => isGoing ? removeAttendMutation.mutate() : attendMutation.mutate("going")}
            >
              <CheckCircle2 size={16} aria-hidden />
              {isGoing ? "Going ✓" : "I'm Going"}
            </Button>
            <Button
              variant={isInterested ? "outline" : "secondary"}
              loading={attendMutation.isPending}
              aria-pressed={isInterested}
              onClick={() => isInterested ? removeAttendMutation.mutate() : attendMutation.mutate("interested")}
            >
              {isInterested ? "Interested ✓" : "Interested"}
            </Button>
          </div>
        )}

        {/* Host */}
        <Link
          href={`/profile/${event.host.username}`}
          className="flex items-center gap-3 p-4 rounded-2xl bg-bg-card border border-border hover:border-border-strong transition-colors"
          aria-label={`View ${event.host.full_name}'s profile`}
        >
          <Avatar src={event.host.avatar_url} name={event.host.full_name} size="md" verified={event.host.is_verified} />
          <div className="flex-1 min-w-0">
            <p className="text-xs text-text-muted">Hosted by</p>
            <p className="text-sm font-semibold text-text">{event.host.full_name}</p>
            <p className="text-xs text-text-muted">@{event.host.username}</p>
          </div>
          <span className="text-xs text-primary" aria-hidden>View profile →</span>
        </Link>

        {/* Description */}
        <section aria-labelledby="about-heading">
          <h2 id="about-heading" className="text-base font-bold text-text mb-2">About</h2>
          <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">{event.description}</p>
        </section>

        {/* Tags */}
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-2" aria-label="Event tags">
            {tags.map((tag) => (
              <Badge key={tag} variant="default">
                <Tag size={10} aria-hidden /> #{tag}
              </Badge>
            ))}
          </div>
        )}

        {/* Map placeholder */}
        {event.latitude && event.longitude && (
          <div className="rounded-2xl overflow-hidden border border-border h-40 bg-bg-card flex items-center justify-center"
            role="img" aria-label={`Map showing ${event.venue_name}, ${event.city}`}>
            <div className="text-center space-y-1">
              <MapPin size={24} className="text-primary mx-auto" aria-hidden />
              <p className="text-xs text-text-muted">{event.venue_name}</p>
              <p className="text-xs text-text-muted">{event.city}</p>
            </div>
          </div>
        )}

        {/* Comments */}
        <section aria-labelledby="comments-heading">
          <h2 id="comments-heading" className="text-base font-bold text-text flex items-center gap-2 mb-3">
            <MessageCircle size={18} className="text-primary" aria-hidden />
            Comments {comments && <span>({comments.length})</span>}
          </h2>

          {user && (
            <form
              className="flex gap-2 mb-4"
              onSubmit={(e) => { e.preventDefault(); commentMutation.mutate(); }}
              aria-label="Add a comment"
            >
              <Avatar src={user.avatar_url} name={user.full_name} size="sm" />
              <div className="flex-1 flex gap-2">
                <label htmlFor="comment-input" className="sr-only">Comment</label>
                <input
                  id="comment-input"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Add a comment..."
                  className="flex-1 bg-bg-card border border-border rounded-2xl px-3 py-2 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
                />
                <Button type="submit" size="sm" loading={commentMutation.isPending}>
                  Post
                </Button>
              </div>
            </form>
          )}

          <ol aria-label="Comments" className="space-y-3">
            {comments?.map((c) => (
              <li key={c.id} className="flex gap-2.5">
                <Avatar src={c.user.avatar_url} name={c.user.full_name} size="sm" />
                <div className="flex-1 bg-bg-card rounded-2xl px-3 py-2">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold text-text">@{c.user.username}</span>
                    <time className="text-[10px] text-text-muted" dateTime={c.created_at}>
                      {timeAgo(c.created_at)}
                    </time>
                  </div>
                  <p className="text-sm text-text-secondary">{c.content}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </article>
  );
}
