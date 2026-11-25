# Competitive analysis: Turnup vs Hi.Events vs Luma vs PartyVerse

_November 2026. Turnup is described from this repository's code. Hi.Events, Luma and PartyVerse
are described from their public sites, app-store listings, press and third-party reviews; their
pricing changes often, so check the sources at the end before quoting numbers. PartyVerse is
covered in [section 6](#6-partyverse-pvrsvp)._

_Update: since the first version, Turnup has shipped promo codes, custom registration
questions, Add to calendar, "who's going" avatars, the viewer's ticket on the event page, and a
Get tickets / I'm going bar that stays on screen and opens a registration sheet._

## 1. One-line positioning

| | What it is | Who it's built for | How it makes money |
|---|---|---|---|
| **Turnup** | Nigeria-first event **discovery + ticketing app**, with a **venue marketplace** and a consumer membership (Turnup+) | Attendees in Lagos/Nigeria, local organizers, venues | % fee on paid tickets (admin-set), venue booking commission, Venue Pro, featured slots, Turnup+ |
| **Hi.Events** | Open-source (self-hostable) **ticketing and event-management software**, plus a hosted cloud | Organizers who want low fees and control (conferences, meetups, festivals) | Cloud: ~0.75% + $0.40 per paid ticket; free events free; self-hosted is free |
| **Luma** | Design-led **event pages + community calendars** with a growing discovery layer and mobile apps | Tech, startup, creator and community hosts (mostly US/EU, global reach) | 5% platform fee on paid tickets on the free plan; Luma Plus (~$59/mo annual) drops it to 0% and raises send limits |

The three are not identical competitors. Hi.Events competes with Turnup for the **organizer's
ticketing tool**; Luma competes for the **organizer's tool and the attendee's attention**;
neither competes with Turnup's **venue marketplace**.

## 2. Feature comparison

✅ = has it · ◐ = partial / limited · ❌ = not found · ? = unconfirmed

| Capability | Turnup | Hi.Events | Luma |
|---|---|---|---|
| **Attendee discovery feed** | ✅ For You ranker, trending, free, city/category, search, saved, follows | ❌ (organizer tool, no marketplace) | ✅ Discover pages, city/calendar feeds |
| **Personalised recommendations** | ✅ Activity log → features → ranker with Lagos context (traffic, holidays, payday, rain), embeddings, learned ranker | ❌ | ◐ (curated/featured, little visible personalisation) |
| **Event sourcing / supply bootstrapping** | ✅ AI scout pulls public feeds into pending events | ❌ | ❌ (hosts create) |
| **Local payments (Nigeria)** | ✅ Paystack (cards, transfer, USSD channels), NGN, split payouts | ❌ Stripe-centric | ❌ Stripe-centric |
| **Paid / free / tiered tickets** | ✅ | ✅ (+ donation / pay-what-you-want) | ✅ |
| **Promo / discount codes** | ✅ (added) | ✅ | ✅ |
| **Custom registration questions** | ✅ (added, with CSV export) | ✅ | ✅ |
| **Approval-required RSVPs** | ? | ◐ | ✅ (incl. paid + approval) |
| **Waitlist** | ✅ | ◐ | ✅ |
| **Members' presale / gated tiers** | ✅ Turnup+ presale and members-only tiers | ❌ | ◐ (token/invite gating) |
| **Ticket transfer / resale** | ✅ | ◐ | ◐ |
| **Check-in** | ✅ organizer check-in screens | ✅ check-in lists | ✅ app/web, wallet passes, check-in staff (Plus) |
| **Apple/Google Wallet passes** | ❌ (ticket image generated) | ? | ✅ |
| **Recurring events / series** | ✅ series + templates | ◐ | ✅ calendars, recurring |
| **Co-hosts / team roles** | ✅ co-hosts | ✅ organisation users | ✅ calendar admins (3 free, 5 on Plus) |
| **Communities / followers** | ✅ communities, follows, comments, reviews | ❌ | ✅ calendars with subscribers — Luma's core |
| **Email / newsletter to audience** | ◐ alerts, nudges, search alerts, Thursday picks | ◐ attendee messaging | ✅ invites + newsletters (500/wk free, 5,000/wk Plus) |
| **SMS / WhatsApp** | ✅ SMS, WhatsApp sharing | ❌ | ❌ |
| **Embeddable widget** | ✅ | ✅ (core feature) | ✅ |
| **Virtual events (Zoom etc.)** | ◐ virtual fields | ◐ | ✅ Zoom integration, live |
| **Public API / webhooks for organizers** | ❌ (webhooks are Paystack-inbound only) | ✅ | ✅ (Plus) |
| **Self-hosting / open source** | ❌ | ✅ AGPL | ❌ |
| **Native mobile apps** | ◐ Android (Capacitor); no iOS build | ❌ web only | ✅ iOS + Android |
| **Venue marketplace** (find, quote, deposit, KYC'd venues, agent visits, refunds, disputes) | ✅ unique | ❌ | ❌ |
| **Deals / perks / membership** | ✅ Turnup+, venue deals, Wrapped | ❌ | ❌ |
| **Privacy controls / data rights** | ✅ personalisation & profiling toggles, 180-day retention, consent log (NDPA-friendly) | ✅ self-host = full data control | ◐ standard |

## 3. SWOT-style breakdown

### Turnup

**Strengths**
- **Local fit nobody else has.** Paystack split payments in NGN, SMS, WhatsApp sharing, and a
  ranker that knows Lagos traffic, public holidays, payday and rain. Luma and Hi.Events both
  assume Stripe, USD/EUR and email.
- **Two-sided demand engine.** Turnup is a consumer app (discovery, For You, saved, follows,
  Wrapped) as well as an organizer tool; Hi.Events has no audience to give organizers.
- **Supply bootstrapping.** The AI scout fills the feed before organizers arrive — the
  classic cold-start problem for a marketplace.
- **Venue marketplace is a real moat.** KYC (CAC, ID, bank match), agent site visits, protected
  deposits, refund penalties, disputes and chargebacks are operationally hard to copy and
  create trust in a market where venue fraud is common.
- **Multiple revenue lines** (ticket fee, booking commission, Venue Pro, featured, Turnup+),
  so ticket fees can be priced aggressively against competitors.
- **Serious engineering base**: idempotent payment confirmation, fee snapshot per order,
  migrations checked in CI, e2e scripts, privacy-by-design activity data.

**Weaknesses**
- **Organizer-tool basics are missing**: no promo/discount codes, no custom registration
  questions, no organizer API/webhooks, no wallet passes. These are table stakes on both
  competitors and are what organizers compare first.
- **No iOS app.** In Lagos's nightlife/tech audience, iPhone share is meaningful; Luma ships
  both stores.
- **Breadth vs depth.** Ticketing, discovery, communities, venues, agents, memberships,
  deals, AI scout: a lot of surface for a beta team to keep excellent.
- **Ops-heavy model.** Agent visits, KYC review, refund enforcement and disputes need people;
  margins depend on keeping that efficient.
- **Brand and network effects are still small** vs Luma's host network; recommendations
  only become good with real activity data (the learned ranker is gated for that reason).
- **Single-host assumptions** (uploads volume, one scheduler process) will need work at scale.

**Gaps to close (prioritised)**
1. ~~Promo codes~~ (done). Early-bird / time-boxed pricing already works through tier sale dates.
2. ~~Custom registration questions~~ (done). Approval-required RSVPs still to do.
3. iOS build of the Capacitor app; Apple/Google Wallet passes for tickets.
4. Audience messaging: let organizers email/SMS/WhatsApp followers and past attendees (with send limits as a paid upsell, like Luma).
5. Organizer payouts transparency (statements, payout schedule) and buyer-pays vs absorb-fee toggle.
6. Organizer API + outgoing webhooks (for corporate and conference organizers).
7. Multi-currency / international cards for diaspora buyers (Paystack supports USD for some merchants).
8. Reserved seating (later; matters for theatre, concerts).

**Threats**
- **Luma adds local rails.** Stripe owns Paystack; if Luma enables Paystack/NGN checkout,
  its brand plus design quality would hit Turnup's tech/creator segment hard.
- **Hi.Events + Paystack fork.** It is open source; a Nigerian agency could self-host it with a
  Paystack integration and offer near-zero fees to organizers.
- **Local incumbents**: Tix Africa, Nairabox, Eventbrite, and informal ticketing via
  Instagram/WhatsApp DMs and bank transfers (zero fees, high trust in personal networks).
- **Venue disintermediation**: organizers and venues meet on Turnup, then pay off-platform.
  The spec counters this (contact hidden until booking, protection only for on-platform
  payments, off-platform reports), but it remains the biggest risk to booking revenue.
- **Macro / regulatory**: naira volatility, CBN payment rules, NDPA enforcement, chargeback fraud.

**Opportunities**
- Own "what's on in Lagos this weekend" as the default consumer habit (Thursday picks,
  Wrapped, For You) — neither competitor targets this.
- Bundle venue + ticketing: an organizer who books a venue on Turnup gets ticketing pre-filled
  and discounted fees — a lock-in no competitor can match.
- Expand to Abuja, Port Harcourt, then Accra/Nairobi with the same local-context playbook.

### Hi.Events

**Strengths**
- Open source (AGPL) and self-hostable: zero platform fee, full data ownership.
- Very cheap cloud (~0.75% + $0.40 per paid ticket; free events free).
- Strong organizer feature set for its age: tiered/donation tickets, promo codes, custom
  questions, capacity rules, product add-ons, embeddable widget, check-in lists, webhooks,
  taxes and fees, multi-language.
- Developer goodwill and a community of contributors.

**Weaknesses**
- No consumer audience or discovery: organizers must bring all their own buyers.
- Stripe-dependent payments; no local African rails out of the box.
- Smaller brand and buyer trust than Eventbrite/Luma for large public events.
- No native mobile apps; web check-in only.

**Gaps**: discovery, recommendations, communities/followers, venues, SMS/WhatsApp, mobile apps.

**Threats to it**: low fees are easy to match; Luma and Eventbrite own audiences.
**Threat it poses to Turnup**: price anchor (organizers will ask "why pay more than 0.75%?")
and a ready-made base for a local fork.

### Luma

**Strengths**
- Best-in-class design of event pages and a very fast "create event in a minute" flow.
- Calendars-as-communities: subscribers, newsletters and invites drive repeat attendance.
- Strong network in tech/startup/creator scenes worldwide, including Lagos tech meetups.
- Polished guest management: approval (incl. paid + approval), custom questions, waitlist,
  wallet passes, check-in app, Zoom integration, API on Plus.
- iOS and Android apps with discovery.

**Weaknesses**
- 5% platform fee on the free plan plus Stripe fees; $59/mo Plus to remove it — expensive in
  naira terms.
- Stripe-only payouts; Nigerian businesses can't easily receive money, so Nigerian paid events
  on Luma are hard (most Lagos usage is free RSVPs).
- Discovery is curated and community-led, not personalised for a city's mass market;
  weak fit for nightlife, concerts, owambe-style and mass consumer events.
- No venue sourcing, no SMS/WhatsApp, no local context.

**Gaps**: local payments, local-language/local-context discovery, venues, offline-first
channels (SMS), membership/perks.

**Threat it poses to Turnup**: the default for tech/community organizers in Lagos already;
if it gains local payments it becomes the strongest competitor in that segment.

## 4. Head-to-head summary

| Dimension | Leader | Why |
|---|---|---|
| Nigerian payments and payouts | **Turnup** | Paystack split, NGN, local channels |
| Attendee discovery in Nigeria | **Turnup** | Personalised, local-context feed + AI-scouted supply |
| Organizer feature depth | **Hi.Events / Luma** | Promo codes, questions, API, wallet passes |
| Community building | **Luma** | Calendars, subscribers, newsletters |
| Price for organizers | **Hi.Events** | 0.75% + $0.40, or free self-hosted |
| Design and brand | **Luma** | |
| Venue sourcing and booking | **Turnup** (uncontested) | |
| Mobile apps | **Luma** | iOS + Android vs Turnup Android only |

## 5. Recommended moves for Turnup (next two quarters)

1. **Close table-stakes gaps** so organizers stop comparing features: promo codes, custom
   questions, approval RSVPs, wallet passes, iOS app.
2. **Price against the anchor**: publish a simple fee (e.g. absorbed vs buyer-pays) and keep
   free events free; show it next to "Luma: 5% + Stripe; can't pay out to Nigerian banks".
3. **Win the tech/community segment from Luma** with a "Luma-quality" event page + paid
   tickets in naira + communities that can message members by email/SMS/WhatsApp.
4. **Lean on the moat**: bundle venue booking with ticketing; make verified-venue trust a
   headline brand promise.
5. **Make the consumer habit stick**: weekly picks, push notifications, Wrapped, Turnup+
   perks — the audience is what Hi.Events can never offer organizers.

## Sources

- Hi.Events: [GitHub](https://github.com/HiEventsDev/Hi.Events), [free ticketing page](https://hi.events/free-event-ticketing), [cheapest ticketing (pricing)](https://blog.hi.events/what-is-the-cheapest-site-to-sell-tickets/), [Gappsy review](https://gappsy.com/tools/hi/), [G2](https://www.g2.com/products/hi-events-event-management-ticket-selling-platform/pricing), [Product Hunt](https://www.producthunt.com/p/hi-events/hi-events)
- Luma: [pricing](https://luma.com/pricing), [Luma Plus overview](https://help.luma.com/p/luma-plus), [guest list management](https://help.luma.com/p/managing-your-guest-list), [check-in](https://help.luma.com/p/check-in), [iOS app](https://help.luma.com/p/luma-ios-app), [App Store](https://apps.apple.com/app/id1546150895)
- Turnup: this repository (`README.md`, `docs/venues-spec.md`, `docs/recommendations-spec.md`, `backend/app/`).


## 6. PartyVerse (pv.rsvp)

_The pv.rsvp site itself couldn't be opened from the environment this was written in (network
policy), so this profile is built from search results: app-store listings, the company's
pages, launch press (some of it sponsored) and one hands-on review. Treat feature claims as
the company's own unless noted._

### What it is

- **PiggyVest's events app.** Launched in **September 2025 as "PartyVest"**, "backed by
  PiggyVest and Zrosk". It has since been **renamed PartyVerse ("Events & Giftings")**: the same
  App Store id (6748926356) and Android package (`com.planaparty.app`) now carry the new name.
  The developer is listed as Piggytech Global (© PlanAParty Global Limited). `pv.rsvp` is the
  domain its event and ticket links use.
- **Positioning:** "Plan, Gift & Celebrate". It is an all-in-one app for *throwing* a party
  (birthdays, BBQs, owambe, weddings) that also sells tickets to public events.
- **Platforms:** iOS and Android. "Free to use, no hidden fees" per the App Store; the Play
  listing mentions in-app purchases. No public fee schedule for tickets or gift links was found.

### Features (as described)

| Area | PartyVerse |
|---|---|
| Planning | Create an event, set guest count and budget, a **planner board**, budget tracker, co-planners |
| Money | Each event gets its **own account number** ("Party Bank"): fund it, receive payments and donations, split costs with friends, and **earn daily interest on money sitting there**, on PiggyVest's infrastructure |
| Vendors | Food, drink and rental vendors, which the team says it vets ("verified vendors") |
| Gifting | **Wishlists and gift links** for cash, flowers and hampers. A TechCabal hands-on in Nov 2025 found gifting "isn't live on the app yet" |
| Guests | Invites, RSVP tracking, guest lists, updates to guests, shared memories gallery |
| Discovery and tickets | Explore page of public events, buy tickets, **group tickets**, RSVP to free events, save events |
| Big events | Sold **Wizkid "Golden Circle"** tickets for his Lagos show on 28 Dec 2025 (₦100,000 per Zikoko, ₦150,000 per NotJustOK; promoted through sponsored posts) |
| Virtual events | Listed |

Not found anywhere: promo codes, custom registration questions, approval RSVPs, door check-in
tools, organizer analytics, personalised recommendations, reviews, communities.

### Turnup vs PartyVerse

| | Turnup | PartyVerse |
|---|---|---|
| Core job | Find and buy public events; run them as an organizer; book venues | Plan and pay for *your own* celebration; also sells event tickets |
| Backer and distribution | Independent | **PiggyVest** (a large existing base of Nigerian savers, strong brand trust, press reach) |
| Money | Paystack checkout and split payouts | **Event wallets with interest**, account number per event, cost splitting, contributions |
| Gifting / contributions | ❌ | ✅ (wishlists, gift links; rollout unclear) |
| Discovery | ✅ personalised For You feed with Lagos context, AI-scouted supply, search, follows | ◐ explore page |
| Organizer ticketing tools | ✅ tiers, presales, promo codes, questions, waitlist, check-in, co-hosts, analytics, transfers | ◐ tickets, group tickets; deeper tools not evident |
| Venues and vendors | ✅ **KYC-verified venues**: agent visits, quotes, protected deposits, refund enforcement, disputes | ◐ vetted vendor list (food, drinks, rentals); no venue booking protection described |
| Private party planning (budget, planner board) | ❌ | ✅ |
| Social layer | ✅ communities, comments, reviews, Wrapped | ◐ memories gallery |
| Native apps | ◐ Android only | ✅ iOS + Android |

### SWOT for PartyVerse (from Turnup's point of view)

**Strengths:** PiggyVest's trust and user base, and a ready fintech stack (wallets, interest,
account numbers) that Turnup can't build quickly. It owns the culturally huge *contributions and
gifting* moment (birthday cash, owambe spraying, wedding gifts). It plans private events, a
category Turnup doesn't serve. It has marketing reach: sponsored coverage and big-artist ticketing
(Wizkid).

**Weaknesses:** It is young (Sept 2025), and the marketing ran ahead of the product (gifting
wasn't live at the Nov 2025 review). It went through a rename within months of launch. Public
discovery is shallow, with no evidence of personalisation or local-context ranking. Organizer
tools for public ticketed events look thin. It has vendors but no verified-venue marketplace
with protected deposits.

**Gaps (things it lacks that Turnup has):** organizer-grade ticketing (promo codes, questions,
waitlist, check-in, analytics); a personalised discovery feed; a verified venue marketplace;
communities and reviews.

**Threats to Turnup:**
- **The most direct local threat** of the four products here. It targets the same Lagos
  attendees, and PiggyVest can **cross-sell to its savers** and subsidise fees.
- **Money gravity.** If hosts already keep the event budget in a PartyVerse wallet that earns
  interest, selling tickets there too is the default.
- **Detty December.** It is already selling headline concert tickets, Turnup's highest-value season.
- **Vendors creeping into venues.** Its vendor list could grow to include venues and erode
  Turnup's marketplace moat.

### What Turnup should do about it

1. **Don't fight on fintech.** Compete on what PartyVerse is weak at: the best feed of *what's on in
   Lagos* (personalised, local context, weekly picks) and the best tools for organizers selling
   tickets to the public.
2. **Add a light contributions layer through Paystack:** "chip in / gift the host" links on
   events, and **group tickets with split pay** (one person reserves, friends each pay their share
   before the hold expires). This covers the social-money moment without a wallet.
3. **Make verified venues the headline.** Protected deposits, agent-checked venues and enforced
   refunds are a trust story a vendor list doesn't match. Market it for weddings and owambe venues.
4. **Ship iOS.** PartyVerse is on both stores; Turnup's Android-only app is a visible gap.
5. **Win Detty December early.** Lock in promoters with promo codes, presales, Turnup+ fast-lane
   and check-in. These are features PartyVerse doesn't show for organizers.
6. **Watch these signals:** a PartyVerse fee schedule, organizer tools (check-in or promo codes
   appearing), any "venues" category, and PiggyVest in-app cross-promotion.

### PartyVerse sources

- [PartyVerse on Google Play](https://play.google.com/store/apps/details?id=com.planaparty.app&hl=en), [PartyVerse on the App Store](https://apps.apple.com/us/app/partyverse-events-giftings/id6748926356), [same listing as PartyVest](https://apps.apple.com/us/app/partyvest-events-giftings/id6748926356)
- [partyverse.com](https://www.partyverse.com/), [planning](https://www.partyverse.com/planning), [guests](https://www.partyverse.com/guests), [gifting](https://www.partyverse.com/gifting), [about](https://www.partyverse.com/about-us), [pv.rsvp](https://www.pv.rsvp/), [@partyverseapp on X](https://x.com/partyverseapp?lang=en-GB)
- Launch coverage: [BusinessDay](https://businessday.ng/news/article/partyvest-launches-to-simplify-how-nigerians-plan-and-celebrate-events/), [Techpoint (brand press)](https://techpoint.africa/brandpress/meet-partyvest-the-new-app-helping-nigerians-find-events-celebrate-and-make-memories/), [ThisDay](https://www.thisdaylive.com/2025/11/10/partyvest-new-app-helping-nigerians-find-events-celebrate-and-make-memories/), [BellaNaija](https://www.bellanaija.com/2025/11/partyvest-event-app/), [TechPolyp](https://techpolyp.com/partyvest-the-ultimate-party-app-helping-nigerians-organize-and-discover-parties-and-connect-with-others/)
- Hands-on: [TechCabal: "I tried planning a BBQ on PiggyVest-backed PartyVest"](https://techcabal.com/2025/11/18/how-piggyvest-backed-partyvest-works/), [TechCabal: Detty December apps](https://techcabal.com/2025/12/01/top-apps-for-detty-december/)
- Wizkid ticketing: [BellaNaija (sponsored)](https://www.bellanaija.com/2025/12/wizkid-live-lagos-partyverse-golden-circle/), [Zikoko](https://www.zikoko.com/?p=367251), [NotJustOK](https://notjustok.com/news/how-much-are-wizkids-g-o-a-t-2025-lagos-concert-tickets/)
