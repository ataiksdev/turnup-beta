"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  eventsApi, socialApi, seriesApi, communitiesApi, organizerApi, apiErrorMessage, ApiError,
  type PromoCheck, type RegistrationAnswers,
} from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useOfflineCopy, useOfflineStore } from "@/store/tickets";
import { useOffline } from "@/lib/network";
import { useOfflineImage } from "@/lib/offlineImages";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { EventDetailSkeleton } from "@/components/ui/Skeleton";
import { formatEventDate, formatMoney, formatPrice, parseTags, timeAgo, displayName, safeHref, randomId } from "@/lib/utils";
import {
  Bookmark, BookmarkCheck, Calendar, ExternalLink,
  MapPin, Tag, Users, MessageCircle, CheckCircle2,
  Star, Ticket, Flame, Monitor, AlertCircle,
  Clock, Images, RefreshCw, Share2, X as XIcon, WifiOff,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { publicOrigin, routes } from "@/lib/routes";
import { useRouteParam } from "@/lib/useRouteParam";
import { EventMap } from "@/components/events/EventMap";
import { HideControls } from "@/components/events/HideControls";
import { SimilarEvents } from "@/components/events/SimilarEvents";
import { EventShareMenu, useShareRef } from "@/components/events/EventShareMenu";
import { useEventPageTracking } from "@/lib/useEventPageTracking";
import { EventDeals, EventVenueCard, GuestVenueReview, MembersOnlyNotice, TierPlusBadges } from "@/components/events/EventMarketplace";
import { ActionBarSpace, AddToCalendar, GoingAvatars, YourTicket } from "@/components/events/EventPageExtras";
import { RegisterSheet } from "@/components/events/RegisterSheet";
import { firstMissingAnswer } from "@/components/events/RegistrationFields";

function SeriesSection({ seriesId, currentEventId }: { seriesId: string; currentEventId: string }) {
  const { data: series } = useQuery({
    queryKey: ["series", seriesId],
    queryFn: () => seriesApi.get(seriesId),
  });
  if (!series || series.events.length <= 1) return null;
  const others = series.events.filter((e) => e.id !== currentEventId);
  return (
    <section>
      <h2 className="text-base font-bold text-text mb-2 flex items-center gap-2">
        <RefreshCw size={16} className="text-primary" aria-hidden />
        Part of &quot;{series.title}&quot;
      </h2>
      <div className="space-y-2">
        {others.slice(0, 5).map((e) => (
          <Link key={e.id} href={routes.event(e.slug)}
            className="flex items-center gap-3 p-3 rounded border-2 border-border bg-bg-card hover:border-border-strong transition-colors">
            <span className="w-6 h-6 rounded bg-primary/10 border border-primary/30 flex items-center justify-center text-[10px] font-black text-primary shrink-0">
              {series.events.findIndex((ev) => ev.id === e.id) + 1}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-text truncate">{format(new Date(e.start_date), "EEE, MMM d · h:mm a")}</p>
            </div>
            <span className={cn("px-2 py-0.5 rounded border text-[10px] font-black uppercase",
              e.status === "published" ? "bg-success/10 text-success border-success/30" : "bg-bg-elevated text-text-muted border-border"
            )}>{e.status}</span>
          </Link>
        ))}
        {others.length > 5 && (
          <p className="text-xs text-text-muted text-center">+{others.length - 5} more occurrences</p>
        )}
      </div>
    </section>
  );
}

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export function EventDetailClient() {
  // Path segment on the web build, ?id= in the Capacitor build (see lib/routes.ts).
  const id = useRouteParam("id");
  useShareRef(); // opened from someone's share link: credit them if this person comes
  const { token, user, hasHydrated } = useAuthStore();
  const qc = useQueryClient();

  const { data: liveEvent, isPending: livePending } = useQuery({
    // Keyed on the session too, so the anonymous response (no saved/going state) is replaced
    // once the saved session has loaded.
    queryKey: ["event", id, !!token],
    queryFn: () => eventsApi.get(id, token ?? undefined),
    enabled: hasHydrated && !!id,
  });
  // Events the user has a ticket for or saved are kept on the phone (OfflineSync): offline,
  // the page opens from that copy. Buying, RSVPs and comments need a connection.
  const offlineCopy = useOfflineCopy(user?.id);
  const offline = useOffline();
  const keptEvent = offlineCopy.events[id];
  const event = liveEvent ?? keptEvent;
  const showingKeptCopy = !liveEvent && !!keptEvent;
  const isLoading = livePending && !keptEvent && !offline;
  useEffect(() => {
    if (liveEvent && user) useOfflineStore.getState().setEvent(user.id, liveEvent);
  }, [liveEvent, user]);
  const heroSrc = useOfflineImage(event?.cover_image);

  // Count a view once the event has loaded (the API de-duplicates repeat views).
  const viewedEventId = event?.id;
  useEffect(() => {
    if (viewedEventId) eventsApi.recordView(viewedEventId, token ?? undefined).catch(() => {});
  }, [viewedEventId, token]);

  // Use the real UUID for all subsequent API calls — the URL param may be a slug
  const eid = event?.id ?? "";

  const { data: comments } = useQuery({
    queryKey: ["comments", eid],
    queryFn: () => socialApi.comments(eid),
    enabled: !!eid,
  });

  const { data: tiers } = useQuery({
    queryKey: ["tiers", eid],
    queryFn: () => eventsApi.tiers(eid),
    enabled: !!eid,
  });

  const activeTiers = (tiers ?? []).filter((t) => t.is_active);
  const ticketed = activeTiers.length > 0;

  const { data: questions } = useQuery({
    queryKey: ["questions", eid],
    queryFn: () => eventsApi.questions(eid),
    enabled: !!eid,
  });

  const { data: myTickets } = useQuery({
    queryKey: ["my-tickets", user?.id],
    queryFn: () => organizerApi.myTickets(token!),
    enabled: !!token && !!eid,
  });
  const myOrders = (myTickets ?? []).filter((o) => o.event_id === eid && o.status === "confirmed");

  const { data: reviews } = useQuery({
    queryKey: ["reviews", eid],
    queryFn: () => eventsApi.reviews(eid),
    enabled: !!eid,
  });

  const { data: myReview } = useQuery({
    queryKey: ["my-review", eid],
    queryFn: () => eventsApi.myReview(token!, eid),
    enabled: !!token && !!eid,
  });

  const [comment, setComment]   = useState("");
  const [saved, setSaved]       = useState(event?.is_saved ?? false);
  const [attendance, setAttend] = useState(event?.attendance_status ?? null);
  // The event loads after first render: keep the button in step with it (e.g. "Going" after buying).
  useEffect(() => { setAttend(event?.attendance_status ?? null); }, [event?.attendance_status]);
  const [actionError, setActionError] = useState("");

  // Ticket cart state: tier id -> quantity (0/absent = not in cart). Several tiers can be
  // bought together in one checkout.
  const [cart, setCart] = useState<Record<string, number>>({});
  const [purchaseSuccess, setPurchaseSuccess] = useState(false);
  const [paymentPending, setPaymentPending] = useState(false);
  const idempotencyKeyRef = useRef<string | null>(null);

  // Registration sheet: tickets, promo code and the host's questions in one place.
  const [sheetOpen, setSheetOpen] = useState(false);
  const [answers, setAnswers] = useState<RegistrationAnswers>({});
  const [missingId, setMissingId] = useState<string | null>(null);
  const [sheetError, setSheetError] = useState("");
  const [promoInput, setPromoInput] = useState("");
  const [appliedPromo, setAppliedPromo] = useState<PromoCheck | null>(null);
  const [promoError, setPromoError] = useState("");
  const [promoBusy, setPromoBusy] = useState(false);

  // Waitlist state
  const [waitlisted, setWaitlisted] = useState(event?.is_waitlisted ?? false);
  const [waitlistPos, setWaitlistPos] = useState<number | null>(null);
  // Returning visitors: look up their place in line (it's only in the join response otherwise).
  const { data: waitlistInfo } = useQuery({
    queryKey: ["waitlist-status", eid],
    queryFn: () => eventsApi.waitlistStatus(token!, eid),
    enabled: !!token && !!eid && waitlisted,
    retry: false,
  });
  const shownWaitlistPos = waitlistPos ?? (waitlistInfo ? waitlistInfo.total_ahead + 1 : null);

  // Review state
  const [reviewRating, setReviewRating] = useState(myReview?.rating ?? 0);
  const [reviewBody, setReviewBody]     = useState(myReview?.body ?? "");
  const [hoverStar, setHoverStar]       = useState(0);

  // Share to community state
  const [showShareModal, setShowShareModal] = useState(false);
  const [sharedTo, setSharedTo] = useState<string[]>([]);
  const [shareError, setShareError] = useState("");

  function flashError(msg: string) {
    setActionError(msg);
    setTimeout(() => setActionError(""), 3500);
  }

  const attendMutation = useMutation({
    mutationFn: (v: "going" | "interested" | { status: "going"; answers: RegistrationAnswers }) => {
      if (!token) return Promise.reject();
      return typeof v === "string"
        ? eventsApi.attend(token, eid, v)
        : eventsApi.attend(token, eid, v.status, v.answers);
    },
    onSuccess: (_, v) => {
      setAttend(typeof v === "string" ? v : v.status);
      if (typeof v !== "string") { setSheetOpen(false); setAnswers({}); }
      qc.invalidateQueries({ queryKey: ["event", id] });
      qc.invalidateQueries({ queryKey: ["attendees", eid] });
    },
    onError: (err, v) => {
      const msg = apiErrorMessage(err, "Could not update RSVP. Please try again.");
      if (typeof v === "string") flashError(msg); else setSheetError(msg);
    },
  });

  const removeAttendMutation = useMutation({
    mutationFn: () => token ? eventsApi.removeAttendance(token, eid) : Promise.reject(),
    onSuccess: () => {
      setAttend(null);
      qc.invalidateQueries({ queryKey: ["event", id] });
    },
    onError: (err) => flashError(apiErrorMessage(err, "Could not remove RSVP. Please try again.")),
  });

  const saveMutation = useMutation({
    mutationFn: () => token ? eventsApi.save(token, eid) : Promise.reject(),
    onSuccess: (res) => setSaved(res.saved),
    onError: (err) => flashError(apiErrorMessage(err, "Could not save event. Please try again.")),
  });

  const commentMutation = useMutation({
    mutationFn: () =>
      token && comment.trim()
        ? socialApi.addComment(token, eid, comment.trim())
        : Promise.reject(),
    onSuccess: () => {
      setComment("");
      qc.invalidateQueries({ queryKey: ["comments", eid] });
    },
    onError: (err) => flashError(apiErrorMessage(err, "Could not post comment. Please try again.")),
  });

  function clearCart() {
    setCart({});
    idempotencyKeyRef.current = null;
    setAppliedPromo(null);
    setPromoInput("");
    setAnswers({});
  }

  // Set below by useEventPageTracking (needs the cart, which is worked out after this).
  const paymentClosedRef = useRef<() => void>(() => {});
  const openPaystack = useCallback((pubKey: string, email: string, amountKobo: number, reference: string) => {
    const PaystackPop = (window as any).PaystackPop;
    if (!PaystackPop) return;
    const handler = PaystackPop.setup({
      key: pubKey,
      email,
      amount: amountKobo,
      ref: reference,
      currency: "NGN",
      channels: ["card", "bank", "ussd", "qr", "bank_transfer", "mobile_money"],
      onClose: () => { setPaymentPending(false); paymentClosedRef.current(); },
      callback: async () => {
        try {
          const confirmed = await eventsApi.verifyPayment(token!, eid, reference);
          clearCart();
          if (confirmed.length === 0) {
            // Paid, but the tickets sold out before the payment cleared; the backend has
            // refunded the buyer (or queued the refund) and sent a notification.
            flashError("These tickets sold out before your payment cleared. You'll be refunded — check your notifications.");
          } else {
            setPurchaseSuccess(true);
          }
          qc.invalidateQueries({ queryKey: ["tiers", eid] });
          qc.invalidateQueries({ queryKey: ["event", id] });
          qc.invalidateQueries({ queryKey: ["my-tickets"] });
        } catch {
          flashError("Payment received but verification failed. Check My Tickets.");
        } finally {
          setPaymentPending(false);
        }
      },
    });
    handler.openIframe();
  }, [token, eid, id, qc]);

  const cartItems = Object.entries(cart)
    .filter(([, qty]) => qty > 0)
    .map(([tier_id, quantity]) => ({ tier_id, quantity }));
  const listTotal = cartItems.reduce((sum, item) => {
    const tier = tiers?.find((t) => t.id === item.tier_id);
    return sum + (tier ? tier.price * item.quantity : 0);
  }, 0);
  const cartTotal = appliedPromo ? appliedPromo.total : listTotal;
  const cartKey = cartItems.map((i) => `${i.tier_id}:${i.quantity}`).join(",");

  async function applyPromo(code = promoInput) {
    if (!token || !code.trim() || cartItems.length === 0) return;
    setPromoBusy(true);
    setPromoError("");
    try {
      setAppliedPromo(await eventsApi.promoCheck(token, eid, code.trim(), cartItems));
    } catch (err) {
      setAppliedPromo(null);
      setPromoError(apiErrorMessage(err, "Couldn't check that code."));
    } finally {
      setPromoBusy(false);
    }
  }
  // The discount depends on what's in the cart: work it out again when the cart changes.
  const appliedCode = appliedPromo?.code;
  useEffect(() => {
    if (appliedCode) applyPromo(appliedCode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cartKey]);

  const pageTracking = useEventPageTracking(
    event, { value: cartTotal, count: cartItems.reduce((n, i) => n + i.quantity, 0) }, purchaseSuccess);
  paymentClosedRef.current = pageTracking.onPaymentClosed;
  function changeQty(tier: { id: string; name: string; price: number }, qty: number) {
    setCart((c) => ({ ...c, [tier.id]: qty }));
    pageTracking.onTierChange(tier, qty);
  }

  const purchaseMutation = useMutation({
    mutationFn: () => {
      if (!token || cartItems.length === 0) return Promise.reject();
      if (!idempotencyKeyRef.current) {
        idempotencyKeyRef.current = randomId();
      }
      return eventsApi.checkout(token, eid, cartItems, idempotencyKeyRef.current, {
        ...(appliedPromo ? { promo_code: appliedPromo.code } : {}),
        ...(questions?.length ? { answers } : {}),
      });
    },
    onSuccess: (data) => {
      setSheetOpen(false);
      if (data.is_free) {
        setPurchaseSuccess(true);
        clearCart();
        qc.invalidateQueries({ queryKey: ["tiers", eid] });
        qc.invalidateQueries({ queryKey: ["event", id] });
        qc.invalidateQueries({ queryKey: ["my-tickets"] });
      } else {
        setPaymentPending(true);
        // Load Paystack script if not already present
        if (!(window as any).PaystackPop) {
          const script = document.createElement("script");
          script.src = "https://js.paystack.co/v1/inline.js";
          script.onload = () => openPaystack(data.paystack_public_key, data.email, data.amount_kobo, data.payment_reference);
          // Bad connection or a blocked script: don't leave the button stuck on "Opening payment…".
          script.onerror = () => {
            script.remove();
            setPaymentPending(false);
            flashError("Couldn't open the payment window. Check your connection and try again. Your tickets are held for 30 minutes.");
          };
          document.body.appendChild(script);
        } else {
          openPaystack(data.paystack_public_key, data.email, data.amount_kobo, data.payment_reference);
        }
      }
    },
    onError: (err) => {
      // A retry after an error is a new attempt (the code or answers may have changed).
      idempotencyKeyRef.current = null;
      setSheetError(apiErrorMessage(err, "Could not initiate payment. Please try again."));
    },
  });

  function openRegister() {
    setSheetError("");
    setMissingId(null);
    setSheetOpen(true);
  }

  /** "I'm going" on an event without tickets: straight through, or via the sheet for questions. */
  function startGoing() {
    if (questions?.length) openRegister();
    else attendMutation.mutate("going");
  }

  function submitRegister() {
    setSheetError("");
    const missing = firstMissingAnswer(questions, answers);
    setMissingId(missing?.id ?? null);
    if (activeTiers.length > 0) {
      if (cartItems.length === 0) { setSheetError("Choose at least one ticket."); return; }
      if (missing) { setSheetError(`Please answer: ${missing.label}`); return; }
      purchaseMutation.mutate();
    } else {
      if (missing) { setSheetError(`Please answer: ${missing.label}`); return; }
      attendMutation.mutate({ status: "going", answers });
    }
  }

  const waitlistJoinMutation = useMutation({
    mutationFn: () => token ? eventsApi.waitlistJoin(token, eid) : Promise.reject(),
    onSuccess: (data) => {
      setWaitlisted(true);
      setWaitlistPos(data.position);
    },
    onError: (err) => flashError(apiErrorMessage(err, "Could not join waitlist. Please try again.")),
  });

  const waitlistLeaveMutation = useMutation({
    mutationFn: () => token ? eventsApi.waitlistLeave(token, eid) : Promise.reject(),
    onSuccess: () => {
      setWaitlisted(false);
      setWaitlistPos(null);
    },
    onError: (err) => flashError(apiErrorMessage(err, "Could not leave waitlist. Please try again.")),
  });

  const reviewMutation = useMutation({
    mutationFn: () =>
      token && reviewRating > 0
        ? eventsApi.createReview(token, eid, reviewRating, reviewBody || undefined)
        : Promise.reject(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reviews", eid] });
      qc.invalidateQueries({ queryKey: ["my-review", eid] });
    },
  });

  const deleteReviewMutation = useMutation({
    mutationFn: () => token ? eventsApi.deleteReview(token, eid) : Promise.reject(),
    onSuccess: () => {
      setReviewRating(0);
      setReviewBody("");
      qc.invalidateQueries({ queryKey: ["reviews", eid] });
      qc.invalidateQueries({ queryKey: ["my-review", eid] });
    },
    onError: (err) => flashError(apiErrorMessage(err, "Could not delete review. Please try again.")),
  });

  const { data: myCommunities } = useQuery({
    queryKey: ["communities-my"],
    queryFn: () => communitiesApi.my(token!),
    enabled: !!token && showShareModal,
  });

  // Communities that already have this event (shared earlier, by me or another member).
  const { data: alreadyShared } = useQuery({
    queryKey: ["community-shared", eid],
    queryFn: () => communitiesApi.sharedWith(token!, eid),
    enabled: !!token && showShareModal,
  });
  const sharedSlugs = new Set([...sharedTo, ...(alreadyShared?.slugs ?? [])]);

  const shareMutation = useMutation({
    mutationFn: (slug: string) => communitiesApi.shareEvent(token!, slug, eid),
    onMutate: () => setShareError(""),
    onSuccess: (_, slug) => setSharedTo((prev) => [...prev, slug]),
    onError: (err, slug) => {
      // Someone shared it there in the meantime: it's there, which is what was wanted.
      if (err instanceof ApiError && err.status === 409) { setSharedTo((prev) => [...prev, slug]); return; }
      setShareError(apiErrorMessage(err, "Couldn't share the event. Try again."));
    },
  });

  // The share sheet closes with Escape, like any dialog.
  useEffect(() => {
    if (!showShareModal) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setShowShareModal(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showShareModal]);

  if (isLoading) return <EventDetailSkeleton />;

  if (!event) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-3 px-8 text-center">
        <AlertCircle size={40} className="text-border-strong" aria-hidden />
        <p className="text-text-secondary">{offline ? "You're offline" : "Event not found"}</p>
        {offline && (
          <p className="text-sm text-text-muted">
            This event isn&apos;t saved on this phone. Events you have tickets for or saved open offline.
          </p>
        )}
        <Link href="/" className="text-primary text-sm font-medium">← Back to Discover</Link>
      </div>
    );
  }

  const tags    = parseTags(event.tags);
  const isGoing = attendance === "going";
  const isInterested = attendance === "interested";
  // Past events still open (e.g. from an organizer's profile) but can't be bought or RSVP'd to.
  const hasEnded = new Date(event.end_date ?? event.start_date).getTime() <= Date.now();
  const onSale = activeTiers.filter((t) => t.available === null || t.available > 0);
  const ticketsAvailable = onSale.length > 0;
  const cheapest = onSale.length ? Math.min(...onSale.map((t) => t.price)) : 0;
  // The action bar that stays on screen (above the bottom navigation) while scrolling.
  const showActionBar = !hasEnded && !showingKeptCopy && event.status === "published"
    && (ticketed ? (ticketsAvailable || myOrders.length > 0) : true);
  const shareUrl = typeof window !== "undefined"
    ? `${publicOrigin()}/events/${id}`
    : `${SITE}/events/${id}`;

  return (
    <article className={cn("flex flex-col", showActionBar ? "pb-28" : "pb-8")}>
      {showingKeptCopy && (
        <div role="status" className="flex items-center gap-2 px-4 py-2 bg-bg-elevated border-b border-border text-xs text-text-muted">
          <WifiOff size={12} aria-hidden />
          <span>You&apos;re offline. Showing the copy of this event saved on your phone.</span>
        </div>
      )}
      {/* Hero image */}
      <div className="relative h-72 w-full">
        {heroSrc ? (
          <Image
            src={heroSrc}
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
              <EventShareMenu
                eventId={event.id}
                title={event.title}
                url={shareUrl}
                onShared={pageTracking.onShared}
                className="bg-bg/60 backdrop-blur-sm hover:bg-bg/80"
                iconClassName="text-white"
              />
              <button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                aria-label={saved ? "Remove from saved" : "Save event"}
                aria-pressed={saved}
                className="p-2 rounded bg-bg/60 backdrop-blur-sm hover:bg-bg/80 transition-colors disabled:opacity-50"
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
            <span className="flex items-center gap-1 px-2.5 py-1 rounded bg-primary text-on-primary text-xs font-bold">
              <Flame size={11} aria-hidden /> Trending
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
          <div className="flex items-start gap-2.5 text-sm text-text-secondary">
            <Calendar size={16} className="text-primary shrink-0 mt-0.5" aria-hidden />
            <dt className="sr-only">Date</dt>
            <dd>
              <span>{formatEventDate(event.start_date)}</span>
              {event.timezone && (
                <span className="block text-xs text-text-muted mt-0.5">{event.timezone}</span>
              )}
              {!hasEnded && <span className="block mt-1"><AddToCalendar event={event} /></span>}
            </dd>
          </div>
          <div className="flex items-center gap-2.5 text-sm text-text-secondary">
            <MapPin size={16} className="text-primary shrink-0" aria-hidden />
            <dt className="sr-only">Location</dt>
            <dd>
              {event.event_type === "virtual" ? (
                <span className="flex items-center gap-1"><Monitor size={14} aria-hidden /> Online event</span>
              ) : (
                `${event.venue_name}, ${event.address}, ${event.city}`
              )}
            </dd>
          </div>
          <div className="flex items-center gap-2.5 text-sm text-text-secondary">
            <Users size={16} className="text-primary shrink-0" aria-hidden />
            <dt className="sr-only">Attendance</dt>
            <dd>
              <GoingAvatars eventId={eid} goingCount={event.attendees_count}
                interestedCount={event.interested_count} />
            </dd>
          </div>
        </dl>

        {user && <YourTicket eventId={eid} />}

        {/* Price */}
        <div className="p-4 rounded border-2 border-border bg-bg-card">
          <p className="text-xs text-text-muted">Admission</p>
          <p className={`text-xl font-black ${event.is_free ? "text-success" : "text-primary"}`}>
            {formatPrice(event.is_free, event.price_min, event.price_max)}
          </p>
        </div>

        {/* Meeting link for virtual/hybrid events */}
        {safeHref(event.meeting_url) && (attendance === "going") && (
          <a
            href={safeHref(event.meeting_url)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between p-4 rounded border-2 border-primary/30 bg-primary/10 hover:border-primary transition-colors"
          >
            <div>
              <p className="text-xs font-black uppercase tracking-widest text-primary mb-0.5">Join Online</p>
              <p className="text-sm text-text truncate max-w-[220px]">{event.meeting_url}</p>
            </div>
            <ExternalLink size={16} className="text-primary shrink-0" />
          </a>
        )}

        {hasEnded && (
          <div role="status" className="flex items-center gap-3 px-4 py-3 rounded border-2 border-border-subtle bg-bg-elevated">
            <Clock size={18} className="text-text-muted shrink-0" aria-hidden />
            <p className="text-sm text-text-secondary">
              <span className="font-bold text-text">This event has ended.</span>{" "}
              {isGoing ? "You were there." : "Tickets and RSVPs are closed."}
            </p>
          </div>
        )}

        {/* RSVP */}
        {user && !hasEnded && (
          <div className="space-y-2">
            <div className="flex gap-2" role="group" aria-label="RSVP options">
              {/* Ticketed events: going means holding a ticket, so that's the Get tickets button. */}
              {!ticketed && (
                <Button
                  fullWidth
                  variant={isGoing ? "primary" : "secondary"}
                  loading={attendMutation.isPending || removeAttendMutation.isPending}
                  aria-pressed={isGoing}
                  onClick={() => isGoing ? removeAttendMutation.mutate() : startGoing()}
                >
                  <CheckCircle2 size={16} aria-hidden />
                  {isGoing ? "Going ✓" : "I'm Going"}
                </Button>
              )}
              {!(ticketed && isGoing) && <Button
                fullWidth={ticketed}
                variant={isInterested ? "outline" : "secondary"}
                loading={attendMutation.isPending || removeAttendMutation.isPending}
                aria-pressed={isInterested}
                onClick={() => isInterested ? removeAttendMutation.mutate() : attendMutation.mutate("interested")}
              >
                {isInterested ? "Interested ✓" : "Interested"}
              </Button>}
            </div>
            {actionError && (
              <p className="text-xs text-error text-center">{actionError}</p>
            )}
          </div>
        )}

        {/* Share to Community */}
        {user && !hasEnded && (
          <button
            onClick={() => setShowShareModal(true)}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded border-2 border-dashed border-border hover:border-primary hover:text-primary text-text-muted text-xs font-bold uppercase tracking-widest transition-colors"
          >
            <Share2 size={13} /> Share to a Community
          </button>
        )}

        {/* Host */}
        <Link
          href={routes.profile(event.host.username)}
          className="flex flex-col gap-3 p-4 rounded border-2 border-border bg-bg-card hover:border-border-strong transition-colors"
          aria-label={`View ${displayName(event.host)}'s profile`}
        >
          <div className="flex items-center gap-3">
            <Avatar
              src={event.host.avatar_url}
              name={displayName(event.host)}
              size="md"
              verified={event.host.is_verified || !!event.host.is_verified_organizer}
            />
            <div className="flex-1 min-w-0">
              <p className="text-xs text-text-muted">Hosted by</p>
              <p className="text-sm font-semibold text-text">{displayName(event.host)}</p>
              <p className="text-xs text-text-muted">@{event.host.username}</p>
            </div>
            <span className="text-xs text-primary shrink-0" aria-hidden>View profile →</span>
          </div>
          {/* Organizer stats row */}
          <div className="flex items-center gap-3 text-xs text-text-muted flex-wrap">
            {(event.host.events_hosted ?? 0) > 0 && (
              <span className="flex items-center gap-1">
                <Ticket size={11} className="text-primary" aria-hidden />
                {event.host.events_hosted} event{event.host.events_hosted !== 1 ? "s" : ""}
              </span>
            )}
            {event.host.avg_rating && (
              <span className="flex items-center gap-1">
                <Star size={11} className="fill-primary text-primary" aria-hidden />
                {event.host.avg_rating.toFixed(1)}
                {(event.host.review_count ?? 0) > 0 && (
                  <span className="text-text-muted">({event.host.review_count})</span>
                )}
              </span>
            )}
            {event.host.followers_count > 0 && (
              <span>{event.host.followers_count.toLocaleString()} follower{event.host.followers_count !== 1 ? "s" : ""}</span>
            )}
          </div>
          {event.host.bio && (
            <p className="text-xs text-text-secondary leading-relaxed line-clamp-2">{event.host.bio}</p>
          )}
        </Link>

        <HideControls eventId={event.id} hostId={event.host.id} hostName={displayName(event.host)} />

        {event.series_id && <SeriesSection seriesId={event.series_id} currentEventId={event.id} />}

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

        {/* Photo gallery */}
        {event.gallery && Array.isArray(event.gallery) && event.gallery.length > 0 && (
          <section aria-labelledby="gallery-heading">
            <h2 id="gallery-heading" className="text-sm font-black text-text flex items-center gap-2 mb-2">
              <Images size={15} className="text-primary" aria-hidden /> Photos
            </h2>
            <div className="grid grid-cols-3 gap-1">
              {(event.gallery as string[]).map((url, i) => (
                <div key={i} className="aspect-square rounded overflow-hidden border border-border bg-bg-elevated">
                  <img src={url} alt="" className="w-full h-full object-cover" loading="lazy" />
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Venue map + directions (physical and hybrid events) */}
        {event.event_type !== "virtual" && (
          <div ref={pageTracking.mapRef}>
            <EventMap venue={event.venue_name} address={event.address} city={event.city}
              latitude={event.latitude} longitude={event.longitude} />
          </div>
        )}

        {/* Venue marketplace and Turnup+ */}
        {(event.host_venue_id || event.venue_id) && <EventVenueCard event={event} />}
        {event.members_only && <MembersOnlyNotice />}
        <EventDeals eventId={event.id} />
        <GuestVenueReview event={event} />

        {/* Ticket tiers */}
        {tiers && tiers.length > 0 && !hasEnded && (
          <section aria-labelledby="tickets-heading" ref={pageTracking.ticketsRef}>
            <h2 id="tickets-heading" className="text-base font-bold text-text flex items-center gap-2 mb-3">
              <Ticket size={18} className="text-primary" /> Tickets
            </h2>

            {purchaseSuccess && (
              <div className="mb-3 px-4 py-3 rounded border-2 border-success/40 bg-success/10 text-sm text-success font-bold">
                ✓ Ticket confirmed! You're going.
              </div>
            )}

            <div className="space-y-2">
              {activeTiers.map((tier) => {
                const available = tier.available;
                const soldOut = available !== null && available <= 0;
                return (
                  <div key={tier.id} className={cn("rounded border-2 border-border p-3", soldOut && "opacity-60")}>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-bold text-text text-sm">{tier.name}</p>
                        {tier.description && <p className="text-xs text-text-muted">{tier.description}</p>}
                        <TierPlusBadges tier={tier} />
                        {available !== null && (
                          <p className="text-xs text-text-muted mt-0.5">
                            {soldOut ? "Sold out" : `${available} left`}
                          </p>
                        )}
                      </div>
                      <p className={cn(
                        "text-base font-black shrink-0 ml-3",
                        tier.price === 0 ? "text-success" : "text-primary",
                      )}>
                        {tier.price === 0 ? "Free" : formatMoney(tier.price, tier.currency)}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>

            {event?.refund_policy && (
              <p className="text-xs text-text-muted mt-3">{event.refund_policy}</p>
            )}

            {ticketsAvailable && (
              <div className="mt-3">
                {user ? (
                  <Button fullWidth onClick={openRegister} loading={paymentPending}>
                    <Ticket size={16} aria-hidden /> {myOrders.length ? "Get more tickets" : "Get tickets"}
                  </Button>
                ) : (
                  <Link href="/login"><Button fullWidth>Log in to get tickets</Button></Link>
                )}
              </div>
            )}
          </section>
        )}

        {/* Waitlist */}
        {event?.waitlist_enabled && user && !purchaseSuccess && !hasEnded && (tiers?.every(t => (t.available !== null && t.available <= 0)) || !tiers?.length) && (
          <section className="bg-bg-card border-2 border-border rounded p-4 shadow-brutal-sm space-y-3">
            <div className="flex items-center gap-2">
              <Clock size={16} className="text-primary" />
              <p className="text-sm font-black text-text uppercase tracking-wide">Waitlist</p>
            </div>
            {waitlisted ? (
              <>
                <p className="text-sm text-text-secondary">
                  You're on the waitlist{shownWaitlistPos ? ` at position #${shownWaitlistPos}` : ""}. We'll notify you if a spot opens up.
                </p>
                <Button
                  variant="secondary"
                  fullWidth
                  loading={waitlistLeaveMutation.isPending}
                  onClick={() => waitlistLeaveMutation.mutate()}
                >
                  Leave Waitlist
                </Button>
              </>
            ) : (
              <>
                <p className="text-sm text-text-secondary">This event is sold out. Join the waitlist to be notified if spots open up.</p>
                <Button
                  fullWidth
                  loading={waitlistJoinMutation.isPending}
                  onClick={() => waitlistJoinMutation.mutate()}
                >
                  Join Waitlist
                </Button>
              </>
            )}
          </section>
        )}

        {/* Rate & Review */}
        {user && attendance === "going" && (
          <section aria-labelledby="review-heading">
            <h2 id="review-heading" className="text-base font-bold text-text flex items-center gap-2 mb-3">
              <Star size={18} className="text-primary" /> Rate This Event
            </h2>

            {myReview ? (
              <div className="bg-bg-card border-2 border-border rounded p-4 space-y-2">
                <div className="flex items-center gap-1">
                  {[1,2,3,4,5].map((s) => (
                    <Star key={s} size={18} className={s <= myReview.rating ? "fill-primary text-primary" : "text-border"} />
                  ))}
                  <span className="text-xs text-text-muted ml-2">Your review</span>
                </div>
                {myReview.body && <p className="text-sm text-text-secondary">{myReview.body}</p>}
                <button
                  onClick={() => deleteReviewMutation.mutate()}
                  disabled={deleteReviewMutation.isPending}
                  className="text-xs text-error hover:underline disabled:opacity-50"
                >
                  {deleteReviewMutation.isPending ? "Deleting…" : "Delete review"}
                </button>
              </div>
            ) : (
              <form
                onSubmit={(e) => { e.preventDefault(); reviewMutation.mutate(); }}
                className="bg-bg-card border-2 border-border rounded p-4 space-y-3"
              >
                <div className="flex items-center gap-1">
                  {[1,2,3,4,5].map((s) => (
                    <button
                      key={s}
                      type="button"
                      onMouseEnter={() => setHoverStar(s)}
                      onMouseLeave={() => setHoverStar(0)}
                      onClick={() => setReviewRating(s)}
                      className="p-0.5"
                    >
                      <Star
                        size={24}
                        className={cn(
                          "transition-colors",
                          s <= (hoverStar || reviewRating) ? "fill-primary text-primary" : "text-border",
                        )}
                      />
                    </button>
                  ))}
                </div>
                <textarea
                  value={reviewBody}
                  onChange={(e) => setReviewBody(e.target.value)}
                  placeholder="Share your experience… (optional)"
                  rows={3}
                  maxLength={2000}
                  className="w-full bg-bg border-2 border-border rounded px-3 py-2 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary resize-none"
                />
                <Button
                  type="submit"
                  size="sm"
                  disabled={reviewRating === 0}
                  loading={reviewMutation.isPending}
                >
                  Submit Review
                </Button>
                {reviewMutation.isError && (
                  <p className="text-xs text-error">
                    {(reviewMutation.error as any)?.message ?? "Could not submit review"}
                  </p>
                )}
              </form>
            )}
          </section>
        )}

        {/* Community reviews */}
        {reviews && reviews.length > 0 && (
          <section aria-labelledby="all-reviews-heading">
            <h2 id="all-reviews-heading" className="text-base font-bold text-text flex items-center gap-2 mb-1">
              <Star size={18} className="text-primary" />
              Reviews <span className="text-text-muted font-normal text-sm">({reviews.length})</span>
            </h2>
            {event.avg_rating && (
              <div className="flex items-center gap-2 mb-3">
                <span className="text-2xl font-black text-text">{event.avg_rating.toFixed(1)}</span>
                <div className="flex items-center gap-0.5">
                  {[1,2,3,4,5].map((s) => (
                    <Star key={s} size={14} className={s <= Math.round(event.avg_rating!) ? "fill-primary text-primary" : "text-border"} />
                  ))}
                </div>
                <span className="text-xs text-text-muted">from {event.review_count} review{event.review_count !== 1 ? "s" : ""}</span>
              </div>
            )}
            <div className="space-y-3">
              {reviews.map((r) => (
                <div key={r.id} className="flex gap-2.5">
                  <Avatar src={r.avatar_url} name={r.full_name ?? r.username} size="sm" />
                  <div className="flex-1 bg-bg-card border-2 border-border rounded px-3 py-2">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-text">@{r.username}</span>
                      <div className="flex items-center gap-0.5">
                        {[1,2,3,4,5].map((s) => (
                          <Star key={s} size={10} className={s <= r.rating ? "fill-primary text-primary" : "text-border"} />
                        ))}
                      </div>
                    </div>
                    {r.body && <p className="text-sm text-text-secondary">{r.body}</p>}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <SimilarEvents eventId={event.id} />

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
              <Avatar src={user.avatar_url} name={displayName(user)} size="sm" />
              <div className="flex-1 flex flex-col gap-1">
                <div className="flex gap-2">
                  <label htmlFor="comment-input" className="sr-only">Comment</label>
                  <input
                    id="comment-input"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Add a comment..."
                    className="flex-1 bg-bg-card border-2 border-border rounded px-3 py-2 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
                  />
                  <Button type="submit" size="sm" loading={commentMutation.isPending}>
                    Post
                  </Button>
                </div>
                {commentMutation.isError && (
                  <p className="text-xs text-error">
                    {(commentMutation.error as any)?.message ?? "Could not post comment"}
                  </p>
                )}
              </div>
            </form>
          )}

          <ol aria-label="Comments" className="space-y-3">
            {comments?.map((c) => (
              <li key={c.id} className="flex gap-2.5">
                <Avatar src={c.user.avatar_url} name={displayName(c.user)} size="sm" />
                <div className="flex-1 bg-bg-card border-2 border-border rounded px-3 py-2">
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

      {showActionBar && <ActionBarSpace />}
      {showActionBar && (
        <div className="fixed inset-x-0 z-40 px-3 pointer-events-none"
          style={{ bottom: "calc(4.5rem + env(safe-area-inset-bottom))" }}>
          <div className="max-w-lg mx-auto pointer-events-auto flex items-center gap-3 p-2.5 pl-4 rounded-lg border-2 border-border bg-bg-surface shadow-brutal">
            <div className="flex-1 min-w-0">
              {ticketed && myOrders.length > 0 ? (
                <>
                  <p className="text-sm font-black text-success">You&apos;re going ✓</p>
                  <p className="text-xs text-text-muted truncate">{myOrders.reduce((n, o) => n + o.quantity, 0)} ticket(s)</p>
                </>
              ) : ticketed ? (
                <>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-text-muted">{onSale.length > 1 ? "From" : "Price"}</p>
                  <p className={cn("text-base font-black", cheapest === 0 ? "text-success" : "text-text")}>
                    {cheapest === 0 ? "Free" : formatMoney(cheapest, onSale[0]?.currency ?? "NGN")}
                  </p>
                </>
              ) : isGoing ? (
                <p className="text-sm font-black text-success">You&apos;re going ✓</p>
              ) : (
                <>
                  <p className="text-sm font-black text-text truncate">{event.title}</p>
                  <p className="text-xs text-text-muted">{event.is_free ? "Free" : formatPrice(event.is_free, event.price_min, event.price_max)}</p>
                </>
              )}
            </div>
            {!user ? (
              <Link href="/login"><Button size="md">{ticketed ? "Get tickets" : "Log in to RSVP"}</Button></Link>
            ) : ticketed && myOrders.length > 0 ? (
              <Link href={routes.ticket(myOrders[0].id)}><Button size="md" variant="secondary"><Ticket size={15} aria-hidden /> View ticket</Button></Link>
            ) : ticketed ? (
              <Button size="md" onClick={openRegister} loading={paymentPending}>
                <Ticket size={15} aria-hidden /> Get tickets
              </Button>
            ) : isGoing ? (
              <Button size="md" variant="ghost" loading={removeAttendMutation.isPending}
                onClick={() => removeAttendMutation.mutate()}>Can&apos;t go</Button>
            ) : (
              <Button size="md" onClick={startGoing} loading={attendMutation.isPending}>
                <CheckCircle2 size={15} aria-hidden /> I&apos;m going
              </Button>
            )}
          </div>
        </div>
      )}

      <RegisterSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        title={event.title}
        tiers={activeTiers}
        cart={cart}
        onQty={changeQty}
        promo={{
          input: promoInput, setInput: (v) => { setPromoInput(v); setPromoError(""); },
          applied: appliedPromo, apply: () => applyPromo(),
          remove: () => { setAppliedPromo(null); setPromoInput(""); setPromoError(""); },
          error: promoError, busy: promoBusy,
        }}
        questions={questions ?? []}
        answers={answers}
        onAnswers={(a) => { setAnswers(a); setMissingId(null); setSheetError(""); }}
        missingId={missingId}
        refundPolicy={event.refund_policy}
        submitLabel={
          !ticketed ? "Register"
            : cartItems.length === 0 ? "Choose tickets"
            : cartTotal === 0 ? "Get free ticket(s)"
            : `Pay ${formatMoney(cartTotal, "NGN")}`
        }
        submitting={purchaseMutation.isPending || paymentPending || attendMutation.isPending}
        onSubmit={submitRegister}
        error={sheetError}
      />

      {/* Share to Community bottom sheet */}
      {showShareModal && (
        <div
          className="fixed inset-0 z-[60] flex flex-col justify-end bg-black/50"
          onClick={() => setShowShareModal(false)}
        >
          <div
            role="dialog" aria-modal="true" aria-labelledby="share-community-title"
            className="bg-bg rounded-t-2xl border-t-2 border-border max-h-[70vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b-2 border-border">
              <p id="share-community-title" className="font-black text-text uppercase tracking-widest text-xs">Share to Community</p>
              <button autoFocus aria-label="Close" onClick={() => setShowShareModal(false)} className="p-1 rounded hover:bg-bg-elevated transition-colors">
                <XIcon size={16} className="text-text-muted" />
              </button>
            </div>
            {shareError && <p role="alert" className="px-4 pt-3 text-xs text-error">{shareError}</p>}
            <div className="overflow-y-auto flex-1 divide-y divide-border">
              {!myCommunities ? (
                <div className="flex justify-center py-10">
                  <div className="w-6 h-6 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                </div>
              ) : myCommunities.length === 0 ? (
                <div className="py-14 text-center space-y-2">
                  <Users size={28} className="text-border-strong mx-auto" />
                  <p className="text-sm text-text-muted">You haven't joined any communities yet.</p>
                  <Link href="/communities" onClick={() => setShowShareModal(false)} className="text-primary text-xs font-bold">Explore Communities →</Link>
                </div>
              ) : (
                myCommunities.map((c: any) => {
                  const shared = sharedSlugs.has(c.slug);
                  return (
                    <button
                      key={c.id}
                      disabled={shared || shareMutation.isPending}
                      onClick={() => !shared && shareMutation.mutate(c.slug)}
                      className={cn(
                        "w-full flex items-center gap-3 px-4 py-3 hover:bg-bg-elevated transition-colors text-left",
                        shared && "opacity-60",
                      )}
                    >
                      <div className="w-9 h-9 rounded-full bg-bg-elevated flex items-center justify-center shrink-0 overflow-hidden">
                        {c.icon ? <span className="text-lg">{c.icon}</span> : <Users size={16} className="text-text-muted" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-text truncate">{c.name}</p>
                        <p className="text-xs text-text-muted">
                          {shared ? "Shared here" : `${c.member_count} members`}
                        </p>
                      </div>
                      {shared ? (
                        <CheckCircle2 size={16} className="text-success shrink-0" />
                      ) : (
                        <Share2 size={14} className="text-text-muted shrink-0" />
                      )}
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </article>
  );
}
