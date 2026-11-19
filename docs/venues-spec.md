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
| What goes through Turnup | **Deposit and balance** (balance can be paid in parts before the venue's due date). Organizers are motivated to pay on-platform: only Turnup payments are protected |
| Commission | Paid by the venue (deducted from its share) on every payment, admin-configurable |
| Refunds | **Always paid by the venue**, stated in the venue terms and booking policy. The venue funds each refund to Turnup, which passes it to the organizer |
| Venue cancels | Organizer refunded 100%. Turnup **still keeps its commission**, owed by the venue. The venue gets a strike (3 in 12 months suspends the listing); cancellations show on the profile |
| Money the venue owes | Recorded on a **venue balance**, recovered by taking a bigger cut of its next bookings. Venue can pay it off directly. Listing paused after 30 days unpaid |
| Disputes | Either side can open one up to 48h after the booking date. An admin decides using the thread and evidence. A refund the venue owes goes on its balance |
| Venue events | Venues publish their own events **as the host**; organizers can be co-hosts; followers are alerted |
| Agent pay | Outside the app for now; added to admin later |
| Reviews | Two scores: "for organizers" (organizers with a completed booking) and "for guests" (attendees who checked in to an event there) |
| Following | Free for everyone. Turnup+ adds perks |
| Turnup+ perks | Presale, priority waitlist, early alerts, members-only events and guest lists, fast lane, member deals, free ticket transfer, weekend picks, Plus badge, Turnup Wrapped (4.8). Not now: booking-fee waiver, monthly credit, cancel-for-credit, group hold |
| Prices | All admin-configurable, with suggested starting values (section 7) |

---

## 2. Roles and who sees what

`users.role` stays as it is (attendee / organizer / moderator / admin). New access comes from
separate tables, so one person can be an attendee, a venue manager and an agent at once.

| Who | How it's recorded | Can |
|---|---|---|
| Venue Owner | `venue_members.role = owner` | Everything for the venue, including bank details, team, Pro and featured purchases, closing the venue |
| Venue Manager | `venue_members.role = manager` | Listing, spaces, calendar, enquiries, quotes, events, deals. Not bank details, team or billing |
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
  link to a Turnup event), starts_at, ends_at, total_kobo, deposit_kobo, balance_due_at,
  paid_kobo (sum of successful payments), commission_percent (snapshot), commission_kobo,
  status (`pending_payment | confirmed | fully_paid | cancelled_by_organizer |
  cancelled_by_venue | cancelled_unpaid_balance | completed | disputed`), refunded_kobo,
  cancelled_at, cancel_reason, completed_at.
- **venue_payments**: every payment on a booking (deposit, balance parts, refund funding).
  id, booking_id, kind (`deposit | balance | refund_funding | debt_payment`), amount_kobo,
  commission_kobo, recovery_kobo, venue_share_kobo, paystack_reference, status
  (`pending | success | failed | refunded | partially_refunded`), paid_at.
- **refund_requests**: id, booking_id, dispute_id (nullable), reason
  (`organizer_cancelled | venue_cancelled | dispute | unpaid_balance`), amount_kobo,
  funded_kobo, refunded_kobo, due_at, status (`awaiting_venue | funded | refunded | overdue |
  advanced_by_turnup`), created_at.
- **off_platform_reports**: id, enquiry_id, reporter_id, message_id, status, decided_by.
- **venue_strikes**: id, venue_id, booking_id, reason, created_at (count those in the last
  12 months).
- **venue_ledger** (the venue balance): id, venue_id, kind (`commission_owed | refund_owed |
  recovered | paid_directly | advanced_by_turnup | adjustment`), amount_kobo (positive = venue owes Turnup),
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
- **events** (existing table): add `host_venue_id` (nullable FK: the venue is the host) and
  `venue_id` (nullable FK: where the event takes place; set to the same venue for
  venue-hosted events). Existing `host_id` stays (the person who created it).
- **venues** also gets `balance_due_days` (default 7).
- **deals**: id, venue_id or event_id (one of them), title, description, kind
  (`free_entry | discount | free_item | reserved | other`), valid_from, valid_to,
  max_per_member, is_active (Turnup+ only; see 4.8).
- **deal_redemptions**: deal_id, user_id, code, claimed_at, redeemed_at (checked at the door
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
   - `transaction_charge` = commission + any debt recovery (4.5)
   - `bearer` = `subaccount` (the venue pays Paystack's fee)
4. The Paystack webhook (or the verify call) **confirms** the booking. The dates are blocked,
   both sides are notified and contact details are revealed. The ledger records any debt
   recovered by this payment.
5. Bookings whose deposit isn't paid expire after 30 minutes. They reuse the existing late-payment checks:
   verify with Paystack before expiring, and refund if the slot was taken in the meantime.
6. **The balance (total minus deposit) is also paid through Turnup**, with the same split.
   - Each venue sets the balance due date, as a number of days before the booking
     (default 7). The quote shows the deposit, the balance and the due date.
   - The organizer can pay the balance in one go or in several parts before the due date.
     Each part is a `venue_payments` row.
   - Reminders go out 7, 3 and 1 day(s) before the due date.
   - If the balance is still unpaid 24h after the due date, the venue may cancel. This counts
     as an **organizer cancellation**: the refund follows the venue's preset, and the venue
     gets no strike.
7. The booking is marked `completed` 48h after it ends if no dispute was opened. That unlocks
   the organizer's review.

**Why organizers should pay the balance through Turnup** (shown on the quote, the booking and
the venue page):
- **Turnup Booking Protection** covers only money paid through Turnup. That means refunds
  when the venue cancels, dispute decisions, and the 100% refund guarantee. Money paid
  directly to a venue is not covered.
- **Pay in parts** before the due date, with automatic receipts and invoices (useful for
  companies that need paperwork).
- **Track record.** Only bookings paid fully through Turnup count towards an organizer's
  "Trusted organizer" badge and booking history. Venues can then see the badge on enquiries
  and may prefer those organizers.
- **Reporting.** If a venue asks for payment outside Turnup, the organizer can report it from
  the thread. A confirmed report is a strike for the venue (venue terms forbid it).

Overlap rule: a space can't have two confirmed bookings that overlap. A whole-venue block
blocks every space. A database-level check runs at confirmation time, inside the same
transaction, to stop two payments landing at once.

### 4.3 Cancellations

Refund presets apply to **everything paid through Turnup** (deposit and any balance paid so
far). Default values below are admin-editable.

| Preset | Full refund if cancelled | 50% refund | No refund |
|---|---|---|---|
| Flexible | ≥ 7 days before | 2–7 days | < 48h |
| Moderate | ≥ 30 days before | 7–30 days | < 7 days |
| Strict | ≥ 60 days before | 30–60 days | < 30 days |

**Refunds are paid by the venue, never by Turnup.** The venue terms and the booking policy
shown to both sides say so. With split payments the venue already holds its share, so
every refund works like this:

1. Turnup works out the refund. It creates a **refund request** that the venue must fund, and
   shows the organizer "Refund of ₦X requested from the venue".
2. The venue pays the amount to Turnup from the portal (Paystack checkout) within
   `refund_funding_hours`, suggested 72h.
3. Turnup then refunds the organizer through Paystack, against the original payment(s).
4. **If the venue doesn't pay in time:**
   - the listing is paused,
   - the amount goes on the venue's ledger as `refund_owed`,
   - the recovery cap is lifted: 100% of the venue's share of its next bookings goes to the
     debt until it's paid,
   - each recovered amount is passed straight to the organizer as a refund, and
   - the organizer can see the progress.

   Turnup does not advance its own money. An admin can still choose to, case by case (for
   example a large or reputational case), recorded on the ledger.

Who pays what:

- **The organizer cancels.** The refund follows the preset snapshotted on the booking. The
  venue funds it. Turnup keeps its commission on everything that was paid, so the venue funds
  the refund out of its own share.
- **The venue cancels.** The organizer gets 100% of everything paid. The venue funds all of it,
  including the amount that went to Turnup as commission, so Turnup keeps its commission (as
  you decided). One strike is added; at 3 strikes in 12 months the listing is suspended
  automatically (admins can lift it). The profile shows "N cancellations in the last 12
  months".
- **The balance is overdue and the venue cancels.** Treated as an organizer cancellation
  (4.2 step 6).

### 4.4 Disputes

- Either side can open a dispute from the booking, from when it's confirmed until 48h after
  it ends. Evidence: text, photos and messages from the thread (already on record).
- While a dispute is open, the booking can't be completed or reviewed.
- The admin decides **no refund / partial / full**. Any refund is funded by the venue through
  the same refund request (4.3). Both sides get the decision and the admin's note.

### 4.5 Venue balance (money owed to Turnup)

- Any amount owed is added to `venue_ledger`.
- On the venue's next payments (bookings and venue-hosted ticket sales), Turnup's split takes
  **commission + recovery**. Recovery is capped at `max_recovery_percent` of each payment
  (suggested 50%) so the venue still gets something, **except** for overdue refund requests,
  where the cap is lifted (4.3) and the recovered money is passed on to the waiting organizer
  first.
- The venue can **pay off** the balance at any time (Paystack checkout to Turnup's main
  account).
- If the oldest unpaid amount is older than 30 days, the listing is **paused** (hidden from
  search, no new enquiries, existing bookings unaffected) until it's paid.
- The portal shows the balance, what it's from, and every recovery.

### 4.6 Venue events

- **The venue is the host.** A venue's Owner or Manager creates the event from the portal. It
  is a normal Turnup event with `host_venue_id` set; the event page, tickets, payouts and
  "hosted by" show the venue, not a person. `host_id` keeps the member who created it, for
  audit. Venue Owners and Managers can manage it; Viewers can see it.
- **Organizers can be co-hosts.** The venue invites organizers through the existing co-host
  feature (`EventCoHost`). Co-hosts appear under the venue on the event page and get the same
  co-host permissions as today. Splitting ticket money with co-hosts stays out of scope.
- Ticket money for venue-hosted events goes to the venue's Paystack subaccount, minus the
  normal ticket fee.
- Organizers can link their own events to a venue with `venue_id` (picked from verified
  venues, or set automatically when the event comes from a venue booking). That links the
  event to the venue's "events here" list and to guest reviews.
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

**Billing**
- Monthly or yearly subscription through a Paystack Plan (card, recurring). Settings gets a
  "Turnup+" section: subscribe, see the renewal date, cancel (stays active until the period
  ends).
- Subscription states arrive through Paystack subscription webhooks (`subscription.create`,
  `invoice.payment_failed`, `subscription.disable`, `subscription.not_renew`). If a renewal
  fails, the subscription is `past_due` with a 3-day grace period, then perks stop.
- One helper, `is_plus(user)`, is used by every perk check. The answer is cached on
  `users.plus_until`.

**Perks.** None of these cost Turnup money; organizers and venues opt in where noted.

1. **Presale.** An organizer or venue can mark a ticket tier as a members' presale: only
   members can buy it until `plus_presale_ends_at`, then it opens to everyone or closes,
   whichever the organizer chose. Members get a notification when a presale opens for an
   organizer or venue they follow.
2. **Priority waitlist.** When a spot opens on a sold-out event, members on the waitlist are
   offered it first, then everyone else in order (`EventWaitlist` ordered by is_plus, then
   position).
3. **Early alerts.** Members hear about new events from followed venues **and organizers**
   straight away; everyone else after `turnup_plus_early_alert_hours` (suggested 24h, sent by
   the worker).
4. **Members-only events and guest lists.**
   - An event can be marked members-only: everyone can see it, but only members can RSVP or
     buy, and the page says "Turnup+ members".
   - Organizers and venues can also add a **members' guest list**: a free or discounted tier
     with limited spots, only for members (a ticket tier flagged `members_only`).
5. **Fast lane.** Organizers can switch on a fast lane for an event. Members' tickets show a
   "Fast lane" mark, and the door scanner shows **FAST LANE** in large text when it scans one,
   so staff can send them to the separate queue. The mark is checked when the ticket is
   scanned (not when it was bought), so a lapsed member doesn't get it.
6. **Member deals.** Venues (portal) and organizers (per event) create deals: free entry
   before a time, a discount, a free drink, a reserved table. Members claim a deal and get a
   code, which the door staff check with the same scanner as tickets. One redemption per deal
   per member unless the venue or organizer says otherwise.
7. **Free ticket transfer.** *New feature* (the app has no transfers today). Members can send
   a ticket to another Turnup user before the event, if the organizer allows transfers
   (default on). The old QR code stops working and the new holder gets a new one. Free for
   members; non-members can't transfer for now (a paid transfer for non-members could come
   later).
8. **Weekend picks.** Every Thursday, members get a personal list of events for the weekend
   (push and email). It's built from the existing For You ranking, filtered to the weekend
   and the member's city, with venues and organizers they follow ranked higher.
9. **Plus badge** next to the member's name on their profile, comments, reviews and on
   organizers' guest lists. Members can hide it.
10. **Turnup Wrapped.** Once a year (December), a shareable summary of the year: events
    attended, top venues and organizers, cities, the busiest month, and the people they went
    with the most (only friends who follow each other, and only if both have
    "show me in Wrapped" on). Images are generated on the server for sharing to Instagram
    and WhatsApp. Free users get a short version; members get the full one.

**Data model additions**
- `users.plus_until` (cached from `subscriptions`), `users.show_plus_badge`,
  `users.wrapped_opt_in`.
- `ticket_tiers`: `members_only` (bool), `plus_presale_ends_at`, `presale_then`
  (`open | close`).
- `events`: `members_only` (bool), `fast_lane_enabled` (bool),
  `allow_ticket_transfers` (bool, default true).
- `ticket_transfers`: id, order_id, from_user_id, to_user_id, old_ticket_code,
  new_ticket_code, created_at.
- `deals` and `deal_redemptions` (section 3): owned by a venue or an event.
- `wrapped_reports`: user_id, year, data (JSON), image keys, generated_at.

**Not now:** booking-fee waiver (would need a buyer-side fee), monthly ticket credit,
cancel-for-credit, group hold.

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
  upcoming events here, Follow button, badges (Verified, Pro), member deals, an "Enquire"
  button (organizers) or a "become an organizer" prompt.
- **Enquiries** (organizer tools; also on the organizer dashboard): list and thread view with
  quote cards and an "Accept and pay deposit" button.
- **My venue bookings**: status, contact details once confirmed, cancel (showing the refund
  amount before confirming), open a dispute, leave a review.
- **Following → Venues**; notifications for new venue events.
- **Settings → Turnup+**: subscribe or manage.
- **Turnup+ wallet** (under Tickets): claimed deal codes, fast-lane mark on tickets,
  "Transfer ticket" button.
- **Weekend picks** (For You tab, Thursdays) and **Wrapped** (December, shareable images).
- **Organizer event editor**: members-only toggle, presale and members' guest-list tiers,
  fast lane, ticket transfers, event deals. The door scanner shows FAST LANE and accepts
  deal codes.

### Venue portal (web only, `/venue/...`, not in the Android build)

- Onboarding wizard: details → spaces → photos → pricing and policies → documents → bank →
  submit.
- Dashboard: verification steps, new enquiries, upcoming bookings, balance, strikes.
- Enquiries inbox and thread, with a quote builder (and templates for Pro venues).
- Calendar: bookings and blocks, add/remove blocks.
- Bookings: details, cancel (with a warning about the strike and commission).
- Events: create and manage (reuses the organizer event tools).
- Deals: create, pause, see redemptions; door check-in for deal codes.
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
- **Attendee:** `POST /events/{id}/venue-review`, `GET /me/deals`,
  `POST /deals/{id}/claim`, `POST /tickets/{order_id}/transfer` (members),
  `GET /me/weekend-picks`, `GET /me/wrapped/{year}`.
- **Organizer (Turnup+ options):** tier fields `members_only`, `plus_presale_ends_at`,
  `presale_then`; event fields `members_only`, `fast_lane_enabled`,
  `allow_ticket_transfers`; event deals CRUD; `POST /events/{id}/deals/redeem` (door).
- **Venue portal:** `POST /venue-portal/venues`, `GET/PATCH /venue-portal/venues/{id}`,
  spaces CRUD, `POST .../documents` (private upload), `PUT .../bank` (resolves the name and
  creates the subaccount), `POST .../submit`, enquiries inbox, `POST .../enquiries/{id}/quotes`,
  `POST .../enquiries/{id}/decline`, blocks CRUD, bookings list and cancel, members and
  invites, deals CRUD and `POST .../deals/redeem`, review replies, ledger and
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
| Booking commission (venue pays, on every payment through Turnup: deposit and balance) | **8%** |
| Refund funding deadline | 72 hours |
| Balance due (venue's default) | 7 days before the booking |
| Debt recovery cap per payment | 50% of the venue's share |
| Featured placement | **₦10,000 / week / city**, ₦25,000 / week / whole state, max 3 per place |
| Venue Pro | **₦15,000 / month** (₦150,000 / year) |
| Turnup+ | **₦1,500 / month** (₦15,000 / year) |
| Early alert head start | 24 hours |

These are guesses based on typical Nigerian SaaS and marketplace pricing. Check them against
two or three local venue owners before launch.

Commission is charged on every payment through Turnup. Because the balance also goes through
Turnup, commission covers the whole booking price. A venue that takes the balance in cash
gets a strike for each confirmed report (4.2).

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
- New venue terms: commission on every payment, **the venue pays all refunds** (from its own
  funds, within the funding deadline, including the commission share when the venue
  cancels), recovery from future payouts, no requests for off-platform payment, strikes,
  suspension, disputes, and Turnup's role as a marketplace (not the venue's agent).
- Organizer booking policy (shown on every quote): Turnup Booking Protection covers only
  money paid through Turnup; refunds are funded by the venue and passed on by Turnup; what
  happens if the venue is late funding a refund; balance due date and what happens if it's
  missed.
- Agent contractor agreement with a confidentiality clause.
- Turnup+ terms: auto-renewal, cancellation, and what each perk includes.

---

## 9. Open questions and risks

1. **Paystack refunds on split payments.** A Paystack refund is taken from Turnup's main
   balance. That is why the venue funds each refund first (4.3) before Turnup sends it.
   Still to confirm with Paystack: partial refunds across several payments, and any limits
   on refunding older transactions.
2. **Agent pay** stays outside the app for now; it will be added to admin later.

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
    (presale, priority waitlist, early alerts, members-only events and guest lists, fast lane,
    deals and redemption, ticket transfers, weekend picks, badge, Wrapped).
11. Featured placement purchases and ranking; Venue Pro analytics and limits.
12. Seed data (demo venues, agent, bookings at every stage), tests (backend unit and flow
    tests on SQLite and Postgres, browser E2E for the main journeys), docs, and the Android
    build check that the venue and agent portals are left out of the app.
