# Venue marketplace: spec (draft for review)

Status: **draft, nothing built yet.** Everything below ships in one release.

Venues list their spaces on Turnup. Organizers find them, enquire, get quotes and pay deposits
in the app. Anyone can follow venues; Turnup+ members get extra perks. Turnup earns from
booking commission, Venue Pro subscriptions, featured placement and Turnup+.

---

## 1. Decisions

| Topic | Decision |
|---|---|
| Venue types | Event halls & centres, lounges/clubs/bars, hotels & studios, outdoor & beach |
| Launch area | All of Nigeria (36 states + FCT) |
| Who lists | Self-serve from day one |
| Where venues work | **Web only** (venue portal). The app shows venues to organizers and attendees |
| Organizer app | Same app as attendees, plus organizer web tools (no separate app) |
| Venue team | Owner / Manager / Viewer |
| Verification | CAC certificate, owner/manager ID, bank account name match, site photos/video, plus a Turnup agent visit |
| Go-live rule | Listing goes live after document checks. **Deposits are blocked until the agent visit passes** (enquiries still allowed) |
| Agents | Contractors with a limited **agent** role: see venues assigned in their states, file visit reports |
| KYC storage | Private store, admins and the assigned agent only, every view logged, deleted 12 months after the venue closes |
| Booking | Enquiry, then a message thread with quote cards, then the organizer accepts and pays the deposit |
| Contact details | Hidden until a booking is confirmed |
| Pricing display | Venue chooses: show "from" prices, show ranges, or "price on request" |
| Deposit | Venue chooses (percentage of quote, or fixed amount) |
| Calendar | Venue calendar. Confirmed bookings and manual blocks make dates unavailable |
| Refund policy | Venue picks a preset: Flexible / Moderate / Strict |
| Payment | Paystack **split**: the venue is paid at once; Turnup's commission is taken at payment |
| Commission | Paid by the venue (deducted from its share), admin-configurable |
| Venue cancels | Organizer refunded 100%. Turnup **still keeps its commission**, owed by the venue. The venue gets a strike (3 in 12 months suspends the listing); cancellations show on the profile |
| Money the venue owes | Recorded on a **venue balance**, recovered by taking a bigger cut of its next bookings. Venue can pay it off directly. Listing paused after 30 days unpaid |
| Disputes | Either side can open one up to 48h after the booking date. An admin decides using the thread and evidence. A refund the venue owes goes on its balance |
| Venue events | Venues can publish their own events; followers are alerted |
| Reviews | Two scores: "for organizers" (organizers with a completed booking) and "for guests" (attendees who checked in to an event there) |
| Following | Free for everyone. Turnup+ adds perks |
| Turnup+ perks | Early alerts from followed venues, priority waitlist, venue perks (deals for members), no ticket service fee |
| Prices | All admin-configurable, with suggested starting values (section 7) |

---

## 2. Roles and who sees what

`users.role` stays as it is (attendee / organizer / moderator / admin). New access comes from
separate tables, so one person can be an attendee, a venue manager and an agent at once.

| Who | How it's recorded | Can |
|---|---|---|
| Venue Owner | `venue_members.role = owner` | Everything for the venue, including bank details, team, Pro and featured purchases, closing the venue |
| Venue Manager | `venue_members.role = manager` | Listing, spaces, calendar, enquiries, quotes, events, perks. Not bank details, team or billing |
| Venue Viewer | `venue_members.role = viewer` | Read-only (calendar, enquiries, analytics) |
| Agent | `agents` row (active, with states) | See venues assigned to them, view those venues' KYC documents, file visit reports |
| Admin | `role = admin` | Review documents, assign agents, decide disputes, set prices, suspend venues, view the KYC access log |
| Moderator | `role = moderator` | Moderate venue reviews and photos |

Each venue has exactly one Owner. The Owner can transfer ownership to a Manager.

---

## 3. Data model

New tables (one Alembic migration, `0003_venues`). Money is stored in **kobo (integers)**,
not floats like the older ticket tables.

### Venues

- **venues**: id, slug, name, type (`hall | lounge | hotel_studio | outdoor`), description,
  state, city, address, latitude, longitude, cover_image, gallery (JSON), amenities (JSON list),
  rules, `price_display` (`from | range | on_request`), `refund_preset`
  (`flexible | moderate | strict`), `deposit_type` (`percent | fixed`), `deposit_value`,
  `status` (`draft | in_review | live | suspended | closed`), `verification_status`
  (`none | documents_submitted | documents_approved | visit_passed | rejected`),
  `deposits_enabled` (true only after visit_passed), paystack_subaccount_code,
  bank_name / bank_account_last4 / bank_account_name (no full number stored), `is_pro`,
  pro_until, followers_count, rating_organizers, rating_guests, review counts, strike_count
  (rolling 12 months, derived), created_at, closed_at.
- **venue_spaces**: one venue can have several spaces (main hall, rooftop, VIP lounge). id,
  venue_id, name, description, capacity_seated, capacity_standing, indoor/outdoor, images,
  price_from, price_to (kobo, nullable), price_unit (`per_day | per_hour | per_event`),
  min_hours, is_active.
- **venue_members**: venue_id, user_id, role, invited_by, created_at. Unique (venue_id, user_id).
- **venue_invites**: venue_id, email, role, token hash, expires_at (reuses the existing
  invite-token pattern).
- **venue_blocks**: manual calendar blocks. venue_id, space_id (nullable = whole venue),
  starts_at, ends_at, note.

### Verification

- **venue_documents**: id, venue_id, kind (`cac | owner_id | site_photo | site_video | other`),
  storage_key (private store, see 8.2), original_filename, content_type, size, uploaded_by,
  status (`pending | approved | rejected`), reviewed_by, reviewed_at, rejection_reason,
  delete_after.
- **kyc_access_log**: id, document_id, user_id, action (`view | download`), ip, at.
- **agents**: user_id (PK), states (JSON list), is_active, phone, created_by, created_at.
- **agent_visits**: id, venue_id, agent_id, status
  (`assigned | scheduled | passed | failed | cancelled`), scheduled_for, checked_in_at, check-in
  latitude/longitude, distance_from_venue_m, checklist (JSON), notes, photos (private store keys),
  decided_at.

### Booking

- **venue_enquiries** (one thread per organizer per request): id, venue_id, space_id,
  organizer_id, event_date_start, event_date_end, guest_count, event_type, budget (nullable),
  message, status (`open | quoted | booked | declined | expired | closed`), last_message_at,
  created_at.
- **enquiry_messages**: id, enquiry_id, sender_id, sender_side (`organizer | venue | system`),
  body, attachments (JSON), quote_id (nullable: the message is a quote card), created_at,
  read_at.
- **venue_quotes**: id, enquiry_id, space_id, starts_at, ends_at, total_kobo, deposit_kobo,
  refund_preset (copied from the venue at the time), inclusions, valid_until,
  status (`sent | accepted | superseded | declined | expired`), created_by.
- **venue_bookings**: id, quote_id, venue_id, space_id, organizer_id, event_id (nullable:
  link to a Turnup event), starts_at, ends_at, total_kobo, deposit_kobo,
  commission_percent (snapshot), commission_kobo, venue_share_kobo, paystack_reference,
  status (`pending_payment | confirmed | cancelled_by_organizer | cancelled_by_venue |
  completed | disputed`), refund_kobo, cancelled_at, cancel_reason, completed_at.
- **venue_strikes**: id, venue_id, booking_id, reason, created_at (count those in the last
  12 months).
- **venue_ledger** (the venue balance): id, venue_id, kind (`commission_owed | refund_owed |
  recovered | paid_directly | adjustment`), amount_kobo (positive = venue owes Turnup),
  booking_id, dispute_id, note, created_by, created_at. Balance = sum. `oldest_unpaid_at` drives
  the 30-day pause.
- **venue_disputes**: id, booking_id, opened_by, side, reason (`not_as_listed | venue_no_show |
  organizer_no_show | damage | other`), description, evidence (JSON), status
  (`open | resolved`), resolution (`no_refund | partial | full`), refund_kobo, decided_by,
  decision_note, created_at, resolved_at.

### Social

- **venue_follows**: user_id, venue_id, created_at. Unique pair.
- **venue_reviews**: id, venue_id, author_id, kind (`organizer | guest`), booking_id
  (organizer kind) or event_id (guest kind), rating 1-5, body, venue_reply, is_hidden,
  created_at. Unique (author_id, booking_id) and (author_id, event_id).
- **events** (existing table): add `venue_id` (nullable FK) and `published_by_venue` (bool).
  Organizer events can also link a venue, so guest reviews and the venue's "events here"
  list work.
- **venue_perks**: id, venue_id, title, description, kind (`free_entry | discount | reserved |
  other`), valid_from, valid_to, is_active.
- **perk_redemptions**: perk_id, user_id, code, redeemed_at (the venue checks codes at the door
  like tickets).

### Subscriptions and featured placement

- **subscription_plans**: code (`turnup_plus | venue_pro`), name, amount_kobo, interval
  (`monthly | annually`), paystack_plan_code, is_active.
- **subscriptions**: id, plan_code, user_id (Turnup+) or venue_id (Venue Pro), status
  (`active | non_renewing | past_due | cancelled`), paystack_subscription_code,
  paystack_customer_code, current_period_end, cancelled_at.
- **featured_slots**: id, venue_id, state, city (nullable = whole state), starts_at, ends_at,
  amount_kobo, paystack_reference, status (`pending | active | ended | refunded`).
- **platform_settings** (existing): add venue_commission_percent, featured_week_price_kobo,
  featured_max_per_city, turnup_plus_early_alert_hours, venue_debt_pause_days (30),
  strike_suspend_count (3), dispute_window_hours (48), max_recovery_percent (see 5.4).
- **notifications** (existing): new kinds for enquiries, quotes, bookings, disputes, strikes,
  follows, venue events, verification steps, subscription renewals.

---

## 4. Main flows

### 4.1 Venue sign-up and verification

1. Any signed-in user opens **Venue portal → List your venue** (web) and becomes the Owner.
2. They fill in the listing: details, spaces, photos, pricing display, deposit rule,
   refund preset.
3. They upload documents: CAC, owner ID and site photos/video.
4. They add bank details. The backend resolves the account name with Paystack
   (`/bank/resolve`) and checks it against the CAC or owner name (fuzzy match; a mismatch goes
   to admin review instead of being rejected outright). It then creates the Paystack
   **subaccount**.
5. An admin reviews the documents. If they pass, the venue goes **live** (enquiries open,
   "Verification visit pending" badge, deposits off).
6. The admin (or auto-assignment by state) assigns an agent. The agent schedules the visit,
   checks in at the venue (GPS must be within ~300 m of the pin, or they must explain why),
   completes the checklist (capacity matches, photos match, exits, power/generator, toilets,
   parking, access) and passes or fails the visit.
7. If the visit **passes**, `deposits_enabled = true` and the venue gets a "Verified by Turnup"
   badge. If it **fails**, the venue sees the reasons and can ask for another visit; deposits
   stay off.

### 4.2 Enquiry, quote and booking

1. The organizer opens a venue and picks a space, dates, guest count and message. This creates
   an enquiry and its thread. Contact details (phone, email, exact address if the venue hides
   it) are not shown, and messages with phone numbers or emails get a gentle warning.
2. The venue replies in the thread and sends a **quote card**: space, times, total, deposit
   (pre-filled from the venue's rule), refund preset, inclusions and an expiry. A new quote
   supersedes the old one.
3. The organizer **accepts**. The backend checks the calendar again (no overlapping confirmed
   booking or block for that space), creates a `pending_payment` booking and starts Paystack
   checkout for the deposit with the split:
   - `subaccount` = the venue's subaccount
   - `transaction_charge` = commission + any debt recovery (5.4)
   - `bearer` = `subaccount` (the venue pays Paystack's fee)
4. The Paystack webhook (or the verify call) **confirms** the booking. The dates are blocked,
   both sides are notified and contact details are revealed. The ledger records any debt
   recovered by this payment.
5. Bookings left unpaid expire after 30 minutes. They reuse the existing late-payment checks:
   verify with Paystack before expiring, and refund if the slot was taken in the meantime.
6. The remaining balance (total minus deposit) is paid to the venue off-platform in v1.
   The quote states it.
7. The booking is marked `completed` 48h after it ends if no dispute was opened. That unlocks
   the organizer's review.

Overlap rule: a space can't have two confirmed bookings that overlap. A whole-venue block
blocks every space. A database-level check runs at confirmation time, inside the same
transaction, to stop two payments landing at once.

### 4.3 Cancellations

Refund presets: refunds go to the organizer from the **deposit**. Default values below are
admin-editable.

| Preset | Full refund if cancelled | 50% refund | No refund |
|---|---|---|---|
| Flexible | ≥ 7 days before | 2–7 days | < 48h |
| Moderate | ≥ 30 days before | 7–30 days | < 7 days |
| Strict | ≥ 60 days before | 30–60 days | < 30 days |

- **The organizer cancels.** Turnup calculates the refund from the preset snapshotted on the
  booking and refunds through Paystack. Turnup keeps its commission on the part the venue
  keeps. The refunded part's commission goes back to the organizer, and the venue's share of
  the refund is recovered from the venue as `refund_owed` (the money already settled to the
  venue). *Exact mechanics depend on 9.1.*
- **The venue cancels.** The organizer gets 100% back. The venue owes the refund plus the full
  original commission (`commission_owed`). One strike is added; at 3 strikes in 12 months the
  listing is suspended automatically (admins can lift it). The profile shows "N cancellations
  in the last 12 months".

### 4.4 Disputes

- Either side can open a dispute from the booking, from when it's confirmed until 48h after
  it ends. Evidence: text, photos and messages from the thread (already on record).
- While a dispute is open, the booking can't be completed or reviewed.
- The admin decides **no refund / partial / full**. A refund is paid to the organizer from
  Turnup's balance through a Paystack refund, and the amount goes on the venue's ledger. Both
  sides get the decision and the admin's note.

### 4.5 Venue balance (money owed to Turnup)

- Any amount owed is added to `venue_ledger`.
- On the venue's next bookings, Turnup's split takes **commission + recovery**. Recovery is
  capped at `max_recovery_percent` of each payment (suggested 50%) so the venue still gets
  something.
- The venue can **pay off** the balance at any time (Paystack checkout to Turnup's main
  account).
- If the oldest unpaid amount is older than 30 days, the listing is **paused** (hidden from
  search, no new enquiries, existing bookings unaffected) until it's paid.
- The portal shows the balance, what it's from, and every recovery.

### 4.6 Venue events

- A venue's Owner or Manager can create an event from the portal. It's a normal Turnup event
  with `venue_id` set and `published_by_venue = true`, hosted by that member. Tickets, check-in
  and approval work as they do now, using the existing ticket fee.
- Organizers can link their own events to a venue (chosen from verified venues, or
  automatically when the event comes from a venue booking).
- When a venue publishes an event, followers are notified. **Turnup+ followers are told
  straight away; everyone else after `turnup_plus_early_alert_hours`** (suggested 24h, sent by
  the worker).

### 4.7 Reviews

- **For organizers:** one review per completed booking, by the organizer who booked it.
- **For guests:** one review per attended event at the venue (the ticket was checked in),
  opening when the event ends and closing 14 days later.
- The venue can post one public reply per review. Moderators can hide reviews.
- The profile shows two separate ratings and counts.

### 4.8 Turnup+

- Monthly subscription through a Paystack Plan (card, recurring). The existing billing
  settings page gets a "Turnup+" section: subscribe, see the renewal date, cancel (stays
  active until the period ends).
- Perks:
  1. **Early alerts** from followed venues (4.6).
  2. **Priority waitlist**: when a spot opens, Turnup+ members on the waitlist are offered it
     first, then everyone else in order. The existing `EventWaitlist.position` logic changes
     to order by (is_plus desc, position).
  3. **Venue perks**: venues list deals for members. Members get a code to show at the door
     (checked like tickets), with one redemption per perk per member unless the venue says
     otherwise.
  4. **No ticket service fee**: the existing ticket fee is deducted from the organizer, not
     the buyer. So for a Turnup+ buyer, Turnup takes 0% on that order and the organizer keeps
     the full amount. **Note:** this is a perk organizers benefit from, not the buyer. If you
     want the buyer to save money, ticket fees must first be charged to buyers (a separate
     change). See open question 9.3.
- Subscription states arrive through Paystack subscription webhooks (`subscription.create`,
  `invoice.payment_failed`, `subscription.disable`, `subscription.not_renew`). If a renewal
  fails, the subscription is `past_due` with a 3-day grace period, then perks stop.

### 4.9 Venue Pro

- Monthly plan billed to the venue (Owner's card). Includes:
  - **analytics**: profile views, enquiry → booking conversion, follower growth, top
    referring searches
  - **more photos** (40 vs 12) and **video**
  - **priority in search** (a ranking boost within the same filters, below featured)
  - **more team seats** (10 vs 3)
  - **quote templates** and **saved replies**
  - **Pro badge**
- Lapsing to free keeps the data and hides the extra photos past the limit.

### 4.10 Featured placement

- A venue buys a week in a state (or a city within it). It appears in the "Featured venues"
  strip and at the top of search results for that place, labelled **Featured**.
- At most `featured_max_per_city` (suggested 3) at a time per place, so it keeps its value. The
  checkout shows the available weeks.
- Paid by one-off Paystack payment to Turnup's main account. Only `live`, non-paused venues
  can buy one.

---

## 5. Screens

### App and website (organizers and attendees)

- **Explore → Venues tab**: search with filters (state/city, type, capacity, date available,
  price band, amenities, verified only), map view, Featured strip.
- **Venue page**: gallery, spaces, capacity, amenities, rules, price display, refund preset
  explained, calendar availability (busy/free, no booking details), both ratings, reviews,
  upcoming events here, Follow button, badges (Verified, Pro), Turnup+ perks, an "Enquire"
  button (organizers) or a "become an organizer" prompt.
- **Enquiries** (organizer tools; also on the organizer dashboard): list and thread view with
  quote cards and an "Accept and pay deposit" button.
- **My venue bookings**: status, contact details once confirmed, cancel (showing the refund
  amount before confirming), open a dispute, leave a review.
- **Following → Venues**; notifications for new venue events.
- **Settings → Turnup+**: subscribe or manage.
- **Perk wallet**: Turnup+ codes, under Tickets.

### Venue portal (web only, `/venue/...`, not in the Android build)

- Onboarding wizard: details → spaces → photos → pricing and policies → documents → bank →
  submit.
- Dashboard: verification steps, new enquiries, upcoming bookings, balance, strikes.
- Enquiries inbox and thread, with a quote builder (and templates for Pro venues).
- Calendar: bookings and blocks, add/remove blocks.
- Bookings: details, cancel (with a warning about the strike and commission).
- Events: create and manage (reuses the organizer event tools).
- Perks: create, pause, see redemptions; door check-in for perk codes.
- Reviews: reply.
- Balance: ledger and pay off.
- Team: invite, roles, transfer ownership.
- Billing: Venue Pro, featured weeks, receipts.
- Settings: listing status, close the venue.

### Agent portal (web, `/agent`)

- My venues (assigned, by state), each venue's documents (logged), visit scheduling, check-in
  (uses the browser's location), checklist form, photo upload, pass/fail with notes.

### Admin (existing admin area)

- Venue verification queue (documents, bank name match), agent management (create, states,
  deactivate), assignment, visit reports, disputes queue, venue ledgers and manual
  adjustments, suspensions and strikes, featured slots, subscription plans and prices, the
  KYC access log, and review moderation.

---

## 6. API outline

All under `/api`. Grouped by router (new files `venues.py`, `venue_portal.py`, `agents.py`,
`billing.py`; additions to `admin.py`, `events.py`).

- **Public:** `GET /venues` (search), `GET /venues/featured`, `GET /venues/{slug}`,
  `GET /venues/{id}/availability?from&to`, `GET /venues/{id}/reviews`,
  `GET /venues/{id}/events`, `POST/DELETE /venues/{id}/follow`.
- **Organizer:** `POST /venues/{id}/enquiries`, `GET /me/enquiries`,
  `GET/POST /enquiries/{id}/messages`, `POST /quotes/{id}/accept` (returns the Paystack URL),
  `POST /quotes/{id}/decline`, `GET /me/venue-bookings`, `POST /venue-bookings/{id}/cancel`
  (with a `preview` option that returns the refund amount), `POST /venue-bookings/{id}/disputes`,
  `POST /venue-bookings/{id}/review`.
- **Attendee:** `POST /events/{id}/venue-review`, `GET /me/perks`,
  `POST /perks/{id}/claim`.
- **Venue portal:** `POST /venue-portal/venues`, `GET/PATCH /venue-portal/venues/{id}`,
  spaces CRUD, `POST .../documents` (private upload), `PUT .../bank` (resolves the name and
  creates the subaccount), `POST .../submit`, enquiries inbox, `POST .../enquiries/{id}/quotes`,
  `POST .../enquiries/{id}/decline`, blocks CRUD, bookings list and cancel, members and
  invites, perks CRUD and `POST .../perks/redeem`, review replies, ledger and
  `POST .../ledger/pay`, `POST .../pro` (subscribe), `POST .../featured` (buy a week),
  `GET .../analytics` (Pro only).
- **Agent:** `GET /agent/venues`, `GET /agent/venues/{id}/documents/{doc}` (logged, short-lived
  signed link), `POST /agent/visits/{id}/schedule`, `POST /agent/visits/{id}/check-in`,
  `POST /agent/visits/{id}/report`.
- **Admin:** verification queue and decisions, agents CRUD, assign visits, disputes and
  decisions, ledger adjustments, suspend/unsuspend, plans and prices (extends
  `PATCH /admin/settings`), featured slots, KYC access log.
- **Billing:** `POST /billing/turnup-plus`, `DELETE /billing/turnup-plus`, `GET /billing/me`.
- **Webhook:** the existing Paystack webhook handles the new references (prefixes `vb_` venue
  booking, `vd_` venue debt payment, `vf_` featured) and the subscription events.

Background jobs (worker): expire unpaid bookings, complete bookings after 48h, close the guest
review windows, send delayed (non-Plus) venue event alerts, pause venues with old debt, end
featured slots, subscription grace periods, delete KYC files past `delete_after`.

---

## 7. Suggested prices (all admin settings)

| Item | Suggested starting value |
|---|---|
| Booking commission (venue pays, on the deposit paid through Turnup) | **8%** |
| Debt recovery cap per payment | 50% of the venue's share |
| Featured placement | **₦10,000 / week / city**, ₦25,000 / week / whole state, max 3 per place |
| Venue Pro | **₦15,000 / month** (₦150,000 / year) |
| Turnup+ | **₦1,500 / month** (₦15,000 / year) |
| Early alert head start | 24 hours |

These are guesses based on typical Nigerian SaaS and marketplace pricing. Check them against
two or three local venue owners before launch.

Commission is on the **deposit paid through Turnup**, because that is the only money Turnup
sees. If venues set very small deposits to pay less commission, the fix is a minimum deposit
(e.g. 20%), which is an admin setting.

---

## 8. Security, privacy and legal

### 8.1 Payments
- Amounts are calculated on the server from the quote, never taken from the client.
- The webhook confirms a booking only if the amount, currency and subaccount match the booking
  (the same check the ticket flow uses now).
- No full bank account numbers are stored. Paystack holds them in the subaccount.

### 8.2 KYC files
- Stored in a **separate private directory** (`KYC_DIR`, its own Docker volume), never under
  the public `/api/uploads` route.
- Served only through a short-lived signed URL, after an access check (admin, or the agent
  assigned to that venue). Every view goes in `kyc_access_log`.
- Images are re-encoded (as uploads are now). PDFs are accepted for CAC documents, size-limited,
  and checked by content, not extension.
- Deleted 12 months after the venue closes (job), or when an admin rejects and the venue
  re-uploads.
- Later, encrypt the files at rest with a key from the environment (worth doing before launch).

### 8.3 Legal (NDPA, consumer protection)
- Update the privacy policy: what venue documents are collected, why, who sees them, how long
  they're kept, and the right to deletion.
- New venue terms: commission, the balance and recovery from payouts, strikes, suspension,
  disputes, and Turnup's role as a marketplace (not the venue's agent).
- Agent contractor agreement with a confidentiality clause.
- Turnup+ terms: auto-renewal, cancellation, and what each perk includes.

---

## 9. Open questions and risks

1. **Paystack refunds on split payments.** Need to confirm in Paystack's docs (or with their
   support) whose balance a refund is taken from when the payment was split to a subaccount.
   If it always comes from Turnup's main balance, Turnup pays refunds first and recovers them
   through the venue ledger (the design above already assumes this). Turnup then needs a
   float in its Paystack balance to cover refunds.
2. **Remaining balance off-platform.** v1 only takes the deposit through Turnup. Should the
   full payment go through Turnup later (more commission, more protection)?
3. **"No ticket fee" for Turnup+.** The current ticket fee comes out of the organizer's share,
   not the buyer's. Waiving it for Turnup+ buyers helps organizers, not the member. Options:
   (a) keep it as is (members get nothing visible), (b) start charging a buyer-side service
   fee to non-members only, or (c) replace this perk with something else.
4. **Venue events and venue team accounts.** Venue events are hosted by the member who
   creates them, shown under the venue's name. Is that right, or should a venue be able to
   appear as its own host account?
5. **Agent pay** is handled outside the app in v1. Should the app track visits per agent for
   payment?

---

## 10. Build order (one release, in this order)

1. Migration and models; settings additions; private KYC storage; roles and permission helpers.
2. Venue portal onboarding: listing, spaces, photos, documents, bank and subaccount; admin
   verification queue.
3. Agents: management, assignment, visit flow and portal.
4. Public venue search, venue pages, follows, map, featured strip (data only).
5. Enquiries, threads, quotes, calendar and blocks.
6. Booking payments with split, confirmation, expiry, completion.
7. Cancellations with presets, strikes, the venue ledger, recovery, pay-off, pausing.
8. Disputes (both sides and admin).
9. Venue events (and linking organizer events), early alerts, reviews (both kinds).
10. Subscriptions: plans, Turnup+ and Venue Pro, webhooks, grace periods; Turnup+ perks
    (priority waitlist, venue perks and redemption, ticket fee waiver).
11. Featured placement purchases and ranking; Venue Pro analytics and limits.
12. Seed data (demo venues, agent, bookings at every stage), tests (backend unit and flow
    tests on SQLite and Postgres, browser E2E for the main journeys), docs, and the Android
    build check that the venue and agent portals are left out of the app.
