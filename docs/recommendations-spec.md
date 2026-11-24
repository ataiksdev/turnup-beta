# Recommendations and activity data

What Turnup records about how people use the app, how it turns that into per-person and
per-event numbers, and how the For You feed ranks events from them. Everything runs on the
existing Postgres, API and worker: no Kafka, Flink or Redis (see [Scaling](#scaling) for when
that changes).

```
 app (lib/track.ts) ──POST /api/track──┐
                                       ├──▶ activity_log ──worker──▶ user_features
 API (saves, orders, check-ins...) ────┘        (append-only)    ╲  event_features
                                                                   ╲
                     GET /events/for-you ◀── recommender.py ◀───────┘
                              │
                              └──▶ recs_served row (what was shown, in what order)
```

| Piece | File |
|---|---|
| Tables | `backend/app/models/activity.py`, migration `0008` |
| Ingest, server events, linking, deletion, retention | `backend/app/services/activity.py`, `routers/track.py` |
| Features | `backend/app/services/rec_features.py` |
| Ranker | `backend/app/services/recommender.py` |
| Offline evaluation | `backend/app/services/rec_eval.py` |
| Synthetic demo activity | `backend/app/demo_activity.py` |
| App tracker | `frontend/src/lib/track.ts`, `useCardTracking.ts`, `useEventPageTracking.ts` |
| User controls | `frontend/src/components/settings/DataSettings.tsx`, `PATCH /api/auth/preferences` |

## 1. What is recorded

Every row in `activity_log` has: `name`, `source` (`client` or `server`), `occurred_at`,
`user_id` (when signed in), `anonymous_id` (random id kept on the device), `session_id`
(new after 30 idle minutes), `platform` (web/android/ios), `app_version`, `event_id` (the
Turnup event, when there is one), `surface` (which feed or page), `position`,
`rec_request_id` (the For You response it came from), `is_promoted` (featured), `geo_city`,
`referrer`, `utm_campaign` and `props` (event-specific details below). `geo_lat`/`geo_lon`
are filled only for signed-in users who opted in to profiling **and** already gave the app
location permission (the tracker never asks for it).

### From the app (`POST /api/track`)

| Event | When | `props` and other fields |
|---|---|---|
| `session_started` | first event after 30 idle minutes | `entry_point` (direct, link, campaign), `local_hour`, `day_of_week` |
| `feed_impression` | a card is at least half on screen for 1 second (once per card per feed load) | `surface`, `position`, `rec_request_id`, `is_promoted` |
| `event_clicked` | a card is tapped | same as impression |
| `search_executed` | a search has shown its first page for 1.2 seconds (not every keystroke) | `query`, `tag`, `filters`, `results_count`, `has_more` |
| `event_viewed` | event page loads | `surface`/`position`/`rec_request_id` of the card that led there (or `direct`), `days_until_event` |
| `event_dwell_ended` | leaving the event page (route change, tab or app closed) | `dwell_seconds` (visible time only), `scroll_depth_pct`, `viewed_map`, `viewed_tickets` |
| `event_shared` | share sheet completed or link copied | `share_channel` (`native`, `copy_link`) |
| `ticket_drawer_opened` | the ticket list comes into view | `lowest_available_price`, `days_until_event` |
| `ticket_tier_selected` | a ticket quantity changes | `tier_id`, `tier_name`, `unit_price`, `quantity` |
| `checkout_abandoned` | payment window closed unpaid (`step: payment`), or left the page with tickets chosen (`step: tier_select`) | `cart_value`, `ticket_count` |
| `notification_interacted` | reserved for push/email opens | `campaign_id`, `notification_type`, `action` |

**Surfaces in use:** `for_you`, `for_you_page`, `trending`, `featured`, `free`,
`home_city`, `home_category`, `search`, `discover_trending`, `discover_following`,
`discover_free`, `discover_new`, `direct`.

### From the server (written where it happens; the app can't send these)

| Event | Written in | `props` |
|---|---|---|
| `user_registered` | `POST /auth/register` | `method` |
| `onboarding_completed` | `POST /auth/onboarding` | categories, city, budget, format, goes_out_when |
| `profile_updated` | `PATCH /auth/preferences` | `fields` changed; `values` only for taste fields (age, gender and consent by name only) |
| `event_saved` / `event_unsaved` | `POST /events/{id}/save` | `days_until_event` |
| `rsvp_changed` | `POST`/`DELETE /events/{id}/attend` | `status`, `from`, `days_until_event` |
| `checkout_started` | `POST /events/{id}/tickets/checkout` | `cart_value`, `ticket_count`, tiers |
| `order_completed` | `confirm_order()` (checkout, verify-payment and the Paystack webhook all pass through it) | `order_id`, `tier_id`, `unit_price`, `total_amount`, `fees_amount`, `ticket_count`, `lead_time_hours`, `payment_channel` |
| `order_refunded` | `refund_order()` | `order_id`, `amount` |
| `ticket_transferred` | `POST /tickets/{id}/transfer` | `order_id`, `to_user_id` |
| `event_checked_in` | `POST /events/{id}/checkin` | `order_id`, `admitted`, `minutes_from_start` |
| `event_reviewed` | `POST /events/{id}/reviews` | `rating`, `has_text` |
| `recs_served` | every `GET /events/for-you` | `ranker` version, `event_ids` in order, `personal`, `has_location` |

### How the app sends it

- Events queue in memory and in `localStorage` (`turnup-track-queue`, at most 500), so
  nothing is lost offline or when the app is killed.
- Sent in batches of up to 50: every 5 s on Wi-Fi, every 30 s on mobile data or Data Saver,
  at once when 20 (50 on mobile data) are waiting, and when the app goes to the background
  or the page closes (`fetch` with `keepalive`).
- Each event has its own id; the server ignores ids it has already stored, so retries are safe.
- A batch the server rejects outright (4xx other than 401/429) is dropped so it can't block
  the queue; anything else is retried later.

### What the server accepts

Known client names only, 50 events per batch, `props` up to 2 KB each (server rows: 16 KB),
timestamps more than 5 minutes ahead or 7 days old replaced by the arrival time,
`120/minute` per IP (`RATE_LIMIT_TRACK`).

### Linking signed-out browsing to an account

On sign-in or sign-up the app calls `POST /api/track/identify` with its `anonymous_id`; the
server gives that device's signed-out rows from the last 30 days (`ANONYMOUS_STITCH_DAYS`)
to the account. Every signed-in batch does the same for anything logged signed out since
(e.g. a feed requested before the app loaded the saved sign-in). `GET /events/for-you` reads
the device id from the `X-Anonymous-Id` header so a signed-out session's own browsing
shapes its feed too.

## 2. People's choices and data rights

| Setting (`users`) | Default | Effect |
|---|---|---|
| `personalized_recs` | on | Off: the feed ignores their history and preferences (place, time and popularity only). Tracking continues. |
| `profiling_consent` (+ `profiling_consent_at`) | **off** | On: coordinates are stored, and `peak_hours`, `co_attendee_ids`, `tastemaker_score` and `segments` are computed. Turning it off clears those at once and removes stored coordinates. |
| `birth_year`, `gender` | not given | Self-reported only; never inferred. Used only in `segments`, so only with consent. |

- **Deleting an account** removes its activity rows (including what its devices did while
  signed out) and its `user_features` row immediately.
- **Retention:** rows older than `ACTIVITY_RETENTION_DAYS` (180) are deleted daily (03:47 UTC).
- **Still to do (other branch):** "download my data", a consent-history log, and the Privacy
  Policy and cookie notice text (section 6).

## 3. Features

Computed by the worker (`app/scheduler.py`); `python -m app.cli recs-features` runs both now.
Every function takes `as_of` and reads only data from before it.

### `event_features` (every 15 minutes, events that haven't ended)

| Column | Meaning |
|---|---|
| `impressions_7d`, `clicks_7d`, `views_7d` | distinct people (user or device), host's own activity excluded |
| `saves_7d`, `orders_7d` | from the saves and orders tables |
| `ctr_7d`, `save_rate_7d`, `view_to_order_rate_7d` | smoothed towards platform priors (5%, 8%, 2%) with 20 imaginary views, so a new event isn't 0% or 100% |
| `velocity_1h`, `velocity_24h` | saves + "going" + orders in the window |
| `interest_surge` | last 24 h vs the daily average of the 7 days before |
| `sell_through_pct`, `remaining_tickets` | from ticket tiers (or capacity for free events); null = unlimited |
| `organizer_quality` | Bayesian average rating of the host's events (5 imaginary 3.5-star reviews), +0.1 verified, −0.15 if many no-shows |
| `attendance_reliability` | admitted ÷ sold on the host's past events (needs 5+ tickets) |
| `demand_score` | 0.6 × Wilson lower bound of engagement per view + 0.4 × log velocity; falls back on lifetime counts before tracking existed |

### `user_features` (nightly 03:03 UTC; computed on demand for someone without a row)

| Column | Meaning |
|---|---|
| `category_affinity`, `tag_affinity` | weighted, decayed (30-day half-life) actions per category/tag, scaled so their top is 1. Weights: click 0.5, view 1, long view (15 s+) +1, ticket list 2, share 3, save 3, interested 2, going 4, order 5, checked in +2 |
| `avg_lead_time_hours`, `spontaneity_ratio` | how long before the event they commit; share decided under 48 h |
| `weekend_share` | share of their events on Fri–Sun (Lagos time) |
| `median_ticket_spend`, `max_ticket_spend`, `free_event_share`, `vip_share` | from orders and engaged events |
| `checkout_abandon_rate` | abandoned ÷ ticket lists opened |
| `home_lat`, `home_lon`, `preferred_radius_km` | centre of the events they commit to, and the 80th-percentile distance × 1.5 (5–60 km). From event locations, not from tracking the person |
| `social_affinity_ids` | people they follow + organizers they've gone to twice |
| `share_rate`, `views_30d`, `saves_30d`, `orders_total` | counts |
| `last_active_at`, `lifecycle` | `new`, `active` (≤7 days), `cooling` (≤30), `dormant` |
| `conversion_propensity` | 0–1, high for people browsing and saving but not buying |
| **With consent only:** `peak_hours` | their 3 most common hours to open the app |
| `co_attendee_ids` | opted-in people they've gone to 2+ events with (events under 300 people) |
| `tastemaker_score` | how often their followers commit to an event within 7 days after they do (90 days, log scale 0–1) |
| `segments` | `weekend_warrior`, `planner`/`spontaneous`, `big_spender` (₦30k+), `free_event_hunter`, `vip_buyer`, `tastemaker`, `lapsing_cooling`/`lapsing_dormant`, `age_18-24`…`age_45+`, `gender_*`, and category labels (`nightlife_regular`, `live_music_fan`, `tech_professional`, `foodie`, `arts_and_culture`, `comedy_fan`, `wellness`, `sports_fan`) for categories at least half as strong as their top one |

## 4. The For You ranker (`recommender.py`, version `v2.0`)

1. **Candidates** (up to 600): published events not yet ended, from the soonest 200, top
   150 by demand, 150 in their top categories, 150 in their city, events by organizers in
   `social_affinity_ids`, and events people they follow are going to. Minus events they've
   already saved, RSVP'd "going" to or bought, and their own events.
2. **Hydrate:** their `user_features` row; `event_features` for the candidates; categories
   they looked at in the last hour; how many people they follow (and, with consent, their
   usual crew) are going; cards shown 3+ times in 3 days without a tap.
3. **Score:** sum of named parts (`WEIGHTS`): taste, onboarding picks, this session, tags,
   distance (exp(−km / their radius)) or city, lead-time fit, tonight (afternoon/evening,
   within 8 h, scaled by spontaneity), this week, weekday/weekend preference, price fit
   against median spend or stated budget, format, friends going, followed organizer, crew,
   event quality (CTR and save rate vs priors), organizer quality, demand, selling fast,
   almost sold out, sold out (−3), ignored before, featured, plus a small daily jitter.
   With no history (signed out, new, or personalisation off), demand ×2, tonight ×1.5 and
   distance ×1.3. `lat`/`lon` query parameters (the phone's location) are used for that
   request only and never stored.
4. **Reason:** the biggest positive part becomes the card's label: "Because you like Music",
   "2 people you follow are going", "From Adaeze", "Happening tonight", "Selling fast",
   "Almost sold out", "3 km away", "In Lagos", "Popular right now".
5. **Re-rank for variety:** each slot takes the best remaining event after −0.7 per event
   from the same category and −0.9 per event from the same organizer already above it.
6. **Discovery slots:** positions 4 and 10 (`DISCOVERY_SLOTS`) go to the best-scoring
   event that is new (listed in the last 14 days), seen by fewer than 40 people this week,
   not sold out, from an organizer with quality ≥ 0.4, and still a positive fit for this
   person. An event that ranked into the slot on its own keeps it. Inserted cards say
   "New on Turnup", and `recs_served.props.discovery_ids` records which events held the
   slots, so their click-through can be compared with the slots' usual rate.
7. **Log:** a `recs_served` row with the order shown; the app sends the same
   `rec_request_id` with impressions and clicks, so click-through by position and feed can
   be measured.

## 5. Checking it works

```bash
cd backend
python -m app.cli seed                 # demo data (DEBUG=true)
python -m app.cli seed-activity        # 150 synthetic people, 50 events, 45 days of activity
python -m app.cli recs-eval            # offline evaluation (all in a rolled-back transaction)
```

`recs-eval` takes a cut-off 10 days ago (`--holdout-days`), rebuilds every feature as of then,
ranks each person's feed as it would have looked, and compares it with what they actually
saved, RSVP'd to or bought afterwards (events they had already committed to don't count).
Baselines: most popular first, and random. On the synthetic data (whose people behave
according to tastes the ranker is designed to find, so this is a sanity check, not proof):

| | NDCG@10 | Recall@10 |
|---|---|---|
| Ranker v2.0 | 0.51 | 0.84 |
| Most popular | 0.29 | 0.64 |
| Random | 0.19 | 0.44 |

Useful SQL once real traffic arrives:

```sql
-- Click-through by feed and position, last 7 days
SELECT surface, position,
       count(*) FILTER (WHERE name = 'event_clicked')::float
         / nullif(count(*) FILTER (WHERE name = 'feed_impression'), 0) AS ctr
FROM activity_log
WHERE occurred_at > now() - interval '7 days' AND name IN ('feed_impression', 'event_clicked')
GROUP BY 1, 2 ORDER BY 1, 2;

-- Searches that found nothing (unmet demand)
SELECT lower(props->>'query') AS q, count(*) FROM activity_log
WHERE name = 'search_executed' AND (props->>'results_count')::int = 0
GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
```

## 6. Built elsewhere (separate branch)

These use the data above but are features, not data collection:

1. A/B testing: a fixed group per person, the group saved on `recs_served`.
2. ~~"Not interested" and "Hide this organizer"~~ (done: `hidden_items`, excluded in
   `_exclusions()` and `_hidden_organizers()`).
3. ~~Discovery slots for new events with few impressions~~ (done: section 4, step 6).
4. ~~Similar events / "people who went to X also went to Y"~~ (done: `services/similar.py`,
   `GET /events/{id}/similar`, shown on event and ticket pages). People who committed to X
   (going, saved, bought) and to another upcoming event, scored by shared people ÷ √(its own
   committed people), with at least 2 people in common so a suggestion never reveals one
   person's plans; then same category, tags, city and price, weighted by demand. At most two
   per organizer; never the viewer's own, committed or hidden events.
5. Ranker-driven weekend picks and "almost sold out" / price-drop alerts, with frequency caps.
6. WhatsApp share links with a ref code (feeds a real `tastemaker_score`).
7. Organizer insights: zero-result searches, best day and time, price benchmarks, booking curves.
8. ~~Better search (Postgres full-text, typo tolerance, "notify me")~~ (done: `services/search.py`, `search_alerts`).
9. Data rights: export, consent history, Privacy Policy and cookie notice.
10. Admin data-health page.
11. Lagos context: travel time, rain, payday, holidays.
12. Embeddings (pgvector) and a trained LightGBM ranker, once real data exists.

## Scaling

The ingest (`services/activity.py`: `ingest`, `record`) and the feature lookups (the
`UserFeatures`/`EventFeatures` reads in `recommender.py`) are deliberately small, so they
can be swapped without touching the ranker or the app:

- **Kafka** behind `ingest()` once sustained traffic reaches thousands of events per second,
  or several consumers need the stream (ad billing, fraud, a warehouse).
- **Redis** for features once `/for-you` p95 goes over ~150 ms or several API replicas
  need shared session state.
- **SQL or dbt** for the feature jobs (now Python over bulk queries) past tens of thousands
  of active users.
