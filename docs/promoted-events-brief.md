# Brief: promoted events (sponsored placements in the For You feed)

**For:** whoever builds Turnup's ad product. This brief stands on its own; read
[`recommendations-spec.md`](recommendations-spec.md) alongside it for the data it builds on.
**Status:** not started. Build on its own branch from the default branch
(`claude/build-turnup-platform-hhOzs`), after the prerequisites in section 3.

## 1. Goal

Let organizers pay to show their event higher in the For You feed, without making the feed
worse for attendees. Sponsored and organic events compete on one scale; an irrelevant event
can't buy its way in; organizers pay a fair second price, only for real results; budgets
last through the day; and every charge can be explained and audited.

The design follows a standard unified-value auction: bids normalised to expected revenue per
1,000 impressions (eCPM), blended with organic relevance, cleared by a generalized
second-price (GSP) auction, with budget pacing. It is adapted here to Turnup's stack and
size: Postgres, one API and one worker on docker-compose, no Kafka or Redis, and beta traffic.

## 2. What already exists (use it, don't rebuild it)

| Need | Where |
|---|---|
| Activity log: `feed_impression`, `event_clicked`, `event_viewed` (from the app), `order_completed` (from the server) with `surface`, `position`, `rec_request_id`, `is_promoted` | `backend/app/models/activity.py` (`Activity`), `backend/app/services/activity.py` (`record`, `CLIENT_EVENTS`, `SERVER_EVENTS`) |
| One `recs_served` row per For You response, with `event_ids` in order | `backend/app/services/recommender.py` (`recommend`) |
| Smoothed per-event rates: `ctr_7d`, `save_rate_7d`, `view_to_order_rate_7d` (priors 5% / 8% / 2%) | `event_features`, `backend/app/services/rec_features.py` |
| Quality: `organizer_quality` (0–1), `attendance_reliability` | `event_features` |
| Sold out: `remaining_tickets`, `sell_through_pct` | `event_features` |
| Ranker (`v2.1`): candidates, `score_event()` returning named parts, `rerank()` for variety, `add_discovery()` keeping `DISCOVERY_SLOTS` (3, 9) for new events, `score_all()` for training | `backend/app/services/recommender.py` |
| "Not interested" / "Hide this organizer" (`HiddenItem`, table `hidden_items`), applied in `_exclusions()` and `_hidden_organizers()` | `backend/app/models/discovery.py`, `backend/app/services/hidden.py` |
| Consent history (`ConsentLog`, table `consent_log`) | `backend/app/models/discovery.py`, `backend/app/services/data_rights.py` |
| Learned ranker: LightGBM **lambdarank** over the ranker's named parts, trained at weekly cut-offs, served only with `RANKER_MODEL_PATH` | `backend/app/services/rec_training.py`, `python -m app.cli recs-train` |
| Admin data-health page (click-through by position, discovery vs rest) | `backend/app/services/data_health.py`, `/admin/data-health` |
| Traffic for pacing: `session_started` with `geo_city`, `props.local_hour`, `props.day_of_week` | `activity_log` |
| Paystack: `initialize_transaction`, `verify_transaction`, `refund_transaction`; webhook at `POST /api/events/webhooks/paystack` | `backend/app/services/paystack.py`, `backend/app/routers/events.py` |
| A paid placement product already: venues buy weekly featured slots (`FeaturedSlot`), priced in `platform_settings` (`featured_state_week_kobo`...), paid through `start_turnup_payment()` | `backend/app/models/venue.py`, `backend/app/routers/venue_portal.py`, `backend/app/services/venue_money.py` |
| Admin-set `events.is_featured` (currently the only "promoted" flag; `is_promoted` in the log is set from it) | `backend/app/routers/admin.py` |
| People's data choices: `users.personalized_recs`, `users.profiling_consent`; partner audience `user_features.segments` (consent only) | `backend/app/models/user.py`, `rec_features.py` |
| Synthetic data and offline evaluation: `python -m app.cli seed-activity`, `recs-eval` | `backend/app/demo_activity.py`, `backend/app/services/rec_eval.py` |

The latest migration is `0014`; number yours from `0015` (check again before you start:
other branches keep adding them, and two migrations with the same parent break CI). `backend/app/database.py`
(`POST_BASELINE_COLUMNS`, `_post_baseline_tables`) must list any new tables and columns on
baseline tables, or the migration tests fail.

## 3. Prerequisites (build these first, on the features branch)

1. **A/B testing.** Each person or device gets a fixed bucket; the bucket is saved on every
   `recs_served` row. Needed to set λ (section 5) from measured retention and ticket sales,
   not guesses, and to keep a no-ads holdout group permanently (5–10%).
2. **Click and order probabilities.** The ranker's score is a hand-weighted sum, not a
   probability, but eCPM needs P(click | person, event) and P(order | person, event). The
   learned ranker in `rec_training.py` doesn't give them either: lambdarank learns an
   *order*, not calibrated probabilities.
   - **Phase A** uses the event-level smoothed rates as priors (`ctr_7d`,
     `view_to_order_rate_7d`), adjusted by position (section 5.3). Good enough for pay-per-order.
   - **Phase B** needs a calibrated model trained on the logged impressions, clicks and
     orders: a pointwise LightGBM `binary` objective (or logistic regression) per outcome,
     on the same named-part features `rec_training.py` already builds, plus position as a
     training feature set to a fixed value when predicting, then isotonic calibration on a
     held-out week. Same data gate as the learned ranker (300+ people-weeks). Pay-per-click
     waits for this.

## 4. Phases

| Phase | Ships | Waits for |
|---|---|---|
| **A: MVP** | Campaigns, prepaid credit, **pay per order (CPA) only**, For You feed only, "Sponsored" label, quality floor, ad-load cap, GSP pricing, billing ledger, even hourly pacing, admin approval, organizer report | A/B testing |
| **B** | Pay per click (CPC) with invalid-click controls; calibrated probabilities; traffic-curve pacing with the PID controller | Phase A live, the trained model |
| **C** | Pay per 1,000 impressions (CPM), other surfaces (search, Discover), self-serve without approval, Redis for pacing state | Invalid-traffic detection; Redis only if several API servers or real ad volume |

**Why pay-per-order first:** impressions and clicks are reported by the app, so anyone can
fake them (including a rival burning an organizer's budget). Orders are recorded by the
server where payment is confirmed (`confirm_order()`), so they can't be faked cheaply.

## 5. Ranking and the auction

### 5.1 Expected revenue per 1,000 impressions

```
eCPM(i) = bid_CPM                       billing = CPM
        = 1000 × P(click | u, i) × bid_CPC     billing = CPC
        = 1000 × P(order | u, i) × bid_CPA     billing = CPA_ORDER
```

### 5.2 Quality and the floor

`Q(u, i)` in [0, 1] from the ranker's organic relevance for this person (normalised score),
`organizer_quality` and `attendance_reliability`, e.g. a weighted geometric mean.
**If `Q < τ_min`, the campaign is out of this auction** whatever it bids (`τ_min` a platform
setting, start around the median organic relevance). Also out: sold out
(`remaining_tickets == 0` and no waitlist), already started, members-only events for
non-members, events the person has already saved, RSVP'd to or bought (the ranker's
`_exclusions()`), events they hid and organizers they hid (`_hidden_organizers()`: hiding
an organizer hides their ads too), and campaigns not active, out of budget, or outside their
dates.

### 5.3 Position bias

Click and order rates depend on the slot. Keep a per-position multiplier table
(`position_ctr_factor[k]`), estimated from logged organic impressions and clicks
(`activity_log`, `surface = 'for_you'`), and use rates "at position 0" in eCPM; multiply by
the factor for the slot actually won when converting prices.

### 5.4 Blended score and guardrails

```
TotalScore(u, i) = V_organic(u, i) + λ × eCPM(i) × Q(u, i)
V_organic(u, i)  = ranker score (scaled) + P(order | u, i) × average platform ticket fee
```

A sponsored event keeps its organic value plus the ad lift. λ is a platform setting, set and
re-checked with the A/B test. Then in `rerank()`:

- **Ad load:** at most 1 sponsored card per 5 (`max_ad_density = 0.2`), never two in a row.
- **Top slot:** a sponsored card takes position 0 only if its organic relevance is in the
  top quartile of this request's candidates.
- **One campaign per event per response.** Variety penalties apply to sponsored cards too.
- **Don't take the discovery slots** (`DISCOVERY_SLOTS`, positions 3 and 9): those are for
  new organizers' events nobody has seen yet; a sponsored card goes in another slot.
- **Off for** people with `personalized_recs = false`? Decide (section 10); default: they
  still see ads, but targeted only by the event's context, never their profile.

### 5.5 Generalized second-price clearing

Rank eligible sponsored candidates by `AdRank = eCPM × Q`. The winner of sponsored slot k
pays the least that would still have beaten the next one or the reserve:

```
clearing_eCPM(k) = max(reserve_eCPM, AdRank(k+1) / Q(k) + ε)
CPA price(k) = min(bid_CPA, clearing_eCPM(k) / (1000 × P(order | u, k)))
CPC price(k) = min(bid_CPC, clearing_eCPM(k) / (1000 × P(click | u, k)))
```

The price is fixed when the auction runs and stored with the impression (section 7.1), then
charged only if the billable action happens.

### 5.6 New campaigns

No history: start from a prior (same category × price band averages, from `event_features`),
blended with observed data with weight `n / (n + 500)` over impressions `n`, i.e. the
observed rate takes over after about 500 impressions.

## 6. Data model (all money in kobo, integers, like the rest of the app)

**`ad_campaigns`**: `id`, `event_id` (FK events, cascade), `organizer_id` (FK users),
`billing_model` (`CPA_ORDER` | `CPC` | `CPM`), `max_bid_kobo`, `daily_budget_kobo`,
`total_budget_kobo`, `spent_today_kobo`, `spent_total_kobo`, `start_at`, `end_at`,
`targeting` (JSON: `radius_km`, `cities`, `categories`, and `segments` only if section 8
allows), `status` (`pending_review` | `active` | `paused` | `exhausted` | `ended` |
`rejected`), `review_note`, `reviewed_by_id`, `created_at`, `updated_at`.

**`ad_credit_ledger`** (organizer's prepaid balance; append-only): `id`, `organizer_id`,
`kind` (`top_up` | `charge` | `refund` | `adjustment` | `expiry`), `amount_kobo` (signed),
`campaign_id`, `charge_id`, `payment_reference`, `note`, `created_at`. Balance = sum.
Top-ups go through Paystack into Turnup's own account (no split). `start_turnup_payment()`
is tied to venues (`VenuePayment`), so either generalise it or add an `AdPayment` record
following the same pattern, confirmed by the existing Paystack webhook.

**`ad_impressions`** (one row per sponsored slot served): `id`, `rec_request_id`,
`campaign_id`, `event_id`, `user_id`, `anonymous_id`, `position`, `clearing_ecpm_kobo`,
`price_kobo` (in the campaign's billing unit), `p_click`, `p_order`, `q`, `pacing_rate`,
`runner_up_campaign_id`, `created_at`. This is the auction log Gemini called
`ad_auction_resolved`, kept as a table so billing can join it.

**`ad_charges`** (billing ledger): `id`, `campaign_id`, `impression_id`, `billable` (`order`
| `click` | `impression`), `source_ref` (the order id, or the click's activity id),
`amount_kobo`, `status` (`charged` | `voided`), `created_at`, with a **unique constraint on
(`campaign_id`, `billable`, `source_ref`)**. That replaces the Redis 24-hour key: a repeated
webhook, double tap or retry can't charge twice.

**`ad_pacing`** (Phase A: one row per campaign per hour; Phase B: per 5 minutes):
`campaign_id`, `bucket_start`, `target_kobo`, `actual_kobo`, `participation_rate`.

Add `rec_request_id` and `campaign_id` to the `recs_served` props (sponsored event id →
campaign id), and new server event names in `SERVER_EVENTS`: `ad_charged`, `ad_voided`.
The app needs no tracking change: impressions and clicks already carry `rec_request_id`
and `position`, and the server knows which slots were sponsored.

## 7. Billing rules

### 7.1 What counts

- **CPA_ORDER:** a confirmed order for the event by the same person within **7 days** of
  them clicking that sponsored card (matched through `event_clicked.rec_request_id` →
  `ad_impressions`), last sponsored click wins, charged once per order
  (`source_ref = order id`). Charged in `confirm_order()`'s transaction, never before.
  A refunded order voids its charge (`ad_voided`, credit returned).
- **CPC (Phase B):** a click on the sponsored card, max one charged click per person (or
  device) per campaign per 24 hours, max N per IP per hour, none from the organizer's own
  account or co-hosts, none when the click comes under 300 ms after the impression.
- **CPM (Phase C):** only once invalid-traffic detection exists.

### 7.2 Spend limits

Check `spent_today_kobo + price ≤ daily_budget`, total budget and credit balance in the same
transaction as the charge (row lock on the campaign). A campaign that runs out moves to
`exhausted` and drops out of auctions immediately. Reset `spent_today_kobo` at midnight
Lagos time in the worker.

### 7.3 Corrections

Admins can void charges (credit returned, reason logged). Organizers see every charge with
the order or click it came from.

## 8. Consent, labelling and law

- **Consent changes are already recorded** in `consent_log`; read the person's current
  `profiling_consent` at auction time, never a cached copy.
- **Targeting by profile only with consent.** `segments`, `co_attendee_ids`, peak hours and
  precise location may only be used for people with `profiling_consent = true`. Everyone
  else can only be targeted by the event's context (its category, city, distance from the
  city they chose). Never target by age band or gender for people who haven't consented.
- **"Sponsored" label** on every paid card, visible on the card itself, not just in a menu.
  Nigeria's consumer-protection (FCCPC) and advertising (ARCON) rules expect paid placement
  to be disclosed; confirm the exact wording with counsel.
- **Organizer ad terms:** what's charged and when, refunds for voided charges, prohibited
  content, Turnup's right to reject or pause. Admin approval of each campaign in Phase A
  (reuse the event review pattern: `review_status`, `review_note`).
- **VAT:** ad spend is a taxable service in Nigeria (7.5% at the time of writing); decide
  whether bids are VAT-inclusive and issue receipts.
- **Privacy Policy:** add how activity is used for ad selection and measurement.

## 9. Pacing

- **Phase A:** spread the daily budget evenly over the hours left in the day: each hour's
  target is remaining budget ÷ hours remaining. A campaign whose spend this hour is ahead of
  target enters auctions with probability `p = clip(target / max(actual, 1), 0.1, 1)`.
  A worker job each hour writes `ad_pacing`. With small beta budgets this is enough.
- **Phase B:** traffic-aware targets from `session_started` volume by city, day of week and
  hour (expected share of the day's remaining traffic per 5-minute bucket), and a
  proportional controller on the participation rate:
  `p(t) = clip(p(t−1) + K_p × (target(t−1) − actual(t−1)), p_min, 1)`, state in `ad_pacing`,
  run by the worker every 5 minutes. Move this state to Redis only when several API
  servers read it on every request.

## 10. Open questions for the product owner

1. Do people who switched off personalised recommendations still see ads (context-targeted)?
2. Prepaid credit only, or invoicing for larger organizers?
3. Do venue-hosted events use the venue's featured-slot purchase, campaigns, or both? Should
   both share one admin page and payment record?
4. Reserve price, `τ_min`, λ and ad density: who sets them (admin settings page)?
5. Can organizers see per-ad results only, or also the auction details (runner-up price)?

## 11. API and UI (Phase A)

- Organizer: `POST /api/ads/credit/top-up`, `GET /api/ads/credit` (balance + ledger),
  `POST /api/ads/campaigns`, `PATCH /api/ads/campaigns/{id}` (pause, budget, bid),
  `GET /api/ads/campaigns/{id}/report` (impressions, clicks, orders, spend, cost per order).
- Admin: approve/reject campaigns, void charges, set reserve, `τ_min`, λ, ad density.
  Add sponsored click-through and charges to the data-health page next to organic.
- App: "Sponsored" label on `ForYouCard`/`EventCard` when the event is sponsored in this
  response (add `is_sponsored` to `EventOut`); organizer pages under `/organizer/ads`
  (web only, like the venue portal).

## 12. Tests and acceptance

- Auction unit tests: eCPM per billing model, quality floor, GSP price ≤ bid and ≥ reserve,
  price for a lone bidder = reserve, ties.
- Feed tests: ad density ≤ 20%, no sponsored card at position 0 unless top-quartile
  relevance, sold-out or started events never sponsored, consent rules on targeting.
- Billing tests: one charge per order however many webhooks or retries arrive; refund voids
  the charge; budget, daily cap and credit can't go negative under concurrent orders
  (SQLite and Postgres; CI runs both); organizer's own clicks never charged.
- Offline: extend `recs-eval` to report how organic quality (NDCG@10) changes with ads on
  at a given λ; it must stay within an agreed margin (e.g. 5%).
- Online (A/B, after launch): no significant drop in sessions per person, organic ticket
  orders or 7-day return rate in the ads group against the holdout.

## 13. Don't

- Don't bill on anything the app reports until invalid-traffic controls exist.
- Don't let a bid lift an event past the quality floor or into position 0 on money alone.
- Don't use profile segments, age or gender for people without profiling consent.
- Don't add Redis or Kafka for this in Phase A.
- Don't hide the label.
