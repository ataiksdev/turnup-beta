# Turnup

Event discovery and ticketing: find events, RSVP, buy tickets (Paystack), check in at the
door, run events as an organizer, and moderate as an admin. Plus a **venue marketplace**
(venues list their spaces, organizers enquire, get quotes and pay through Turnup) and
**Turnup+** memberships. Ships as a website and an Android app (Capacitor).

| Part | Stack | Folder |
|---|---|---|
| API | FastAPI, SQLAlchemy 2 (async), Alembic | `backend/` |
| Web app | Next.js 16 (App Router), React 18, TanStack Query, Tailwind | `frontend/` |
| Android app | Capacitor 8 wrapping a static export of the web app (admin pages removed) | `frontend/android/` |

## Local development

**Backend** (SQLite, migrations and background jobs all in one process):

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # DEBUG=true prints emails/SMS to the console and fakes Paystack
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm ci
npm run dev                   # http://localhost:3003; /api/* is proxied to localhost:8000
```

**Demo data** for test/staging (all accounts use the password `password123`):

```bash
cd backend
python -m app.cli seed            # into an empty database
python -m app.cli seed --reset    # wipe everything first (only allowed with DEBUG=true)
python -m app.cli seed-venues     # add the venue demo data to a database seeded before venues existed
```

With Docker: `docker compose run --rm migrate python -m app.cli seed`. It creates an admin
(`admin@turnup.ng`), organizers (`adaeze@`, `seun@`, `dayo@turnup.ng`) and attendees
(`tunde@`, `chiamaka@turnup.ng`), with events, tickets (some checked in), communities,
reviews, comments, a waitlist, and items waiting in the admin approval and verification queues.
For the venue marketplace: a venue owner (`bola@turnup.ng`, at /venue), an agent
(`kemi@turnup.ng`, at /agent), venues at every verification stage, enquiries, bookings, a
refund waiting for the venue, a featured slot and deals; `chiamaka@` is a Turnup+ member.

## Venue marketplace and Turnup+

Spec and decisions: [`docs/venues-spec.md`](docs/venues-spec.md). In short:

| Who | Where |
|---|---|
| Organizers and attendees | `/venues` (search by state, area or near me), venue pages, `/enquiries`, `/venue-bookings`, `/plus` |
| Venue teams (Owner / Manager / Viewer) | `/venue` (web only: listing, verification, payouts, enquiries and quotes, calendar, refunds, team, deals, Pro, featured) |
| Agents | `/agent` (web only: assigned visits, documents, GPS check-in, report) |
| Admins | `/admin/venues`, `/admin/marketplace` (disputes, refunds, reports, chargebacks, agents, areas, prices) |

- Payments go through Paystack **split**: the venue's share goes straight to its subaccount,
  Turnup's commission (and any recovery of what the venue owes) is the `transaction_charge`.
- **Refunds are always paid by the venue.** The venue pays each refund in; Turnup then
  refunds the organizer. Late refunds trigger penalties (pause, recovery from later payouts,
  suspension, a claim pack for the organizer). Turnup never advances its own money.
- Venue verification files are stored privately (`KYC_DIR`, its own Docker volume) and only
  served through short-lived signed links; every view is logged.
- Video uploads use ffmpeg when it's installed (it is in the Docker image).
- The worker runs the marketplace jobs: expiring unpaid checkouts, completing bookings,
  balance reminders, the unpaid-refund penalty timeline, early alerts, subscriptions,
  featured slots, KYC retention, Thursday weekend picks and December Wrapped.

`scripts/e2e/marketplace.js` drives the main journeys in a browser (instructions in the file).

## Recommendations and activity data

Spec: [`docs/recommendations-spec.md`](docs/recommendations-spec.md). The app logs what people
do (feed impressions, clicks, views, searches, ticket choices, shares) to `POST /api/track`,
and the API logs saves, RSVPs, orders, check-ins and reviews itself, all into `activity_log`.
The worker turns that into `event_features` (every 15 minutes) and `user_features` (nightly),
which the `/events/for-you` ranker reads. People control it in Settings > Your data
(personalisation on by default, profiling opt-in off by default); activity is kept 180 days.

```bash
cd backend
python -m app.cli seed-activity    # synthetic people + 45 days of activity (DEBUG=true only)
python -m app.cli recs-features    # recompute features now
python -m app.cli recs-eval        # offline ranker evaluation vs popular/random baselines
```

## Database migrations

The schema is managed by Alembic (`backend/migrations/`). The API applies migrations on
startup by default (`RUN_MIGRATIONS_ON_STARTUP=true`). A database created before migrations
existed is detected, patched and adopted automatically.

After changing a model:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
# review the generated file in migrations/versions/, then
alembic upgrade head
```

CI fails if models and migrations disagree (`tests/test_migrations.py`).

## Process roles

| Command | What it does |
|---|---|
| `uvicorn app.main:app` | The API. Also migrates and runs background jobs unless `RUN_MIGRATIONS_ON_STARTUP=false` / `RUN_SCHEDULER=false` |
| `python -m app.cli migrate` | Upgrades the schema and seeds defaults, then exits |
| `python -m app.worker` | Runs background jobs only: expiring unpaid orders (checks Paystack first) and the daily AI scout |

Run **exactly one** process with the scheduler enabled; otherwise every job runs once per process.

## Deploying

**Recommended (free): backend on an Oracle Cloud VM, website on Vercel, with automatic deploys
from GitHub.** Step-by-step guide: [`deploy/oracle/README.md`](deploy/oracle/README.md).

### Deploying with Docker (any server)

```bash
cp .env.example .env          # set SECRET_KEY, POSTGRES_PASSWORD, SITE_ADDRESS, Paystack/SMTP keys
docker compose up -d --build
```

This starts Postgres, a one-off `migrate` job, the API (2 workers, no jobs), a single
`worker`, the Next.js frontend, and **Caddy** as the only public entry point (ports 80/443).
Caddy sends `/api/*` to the backend and everything else to the frontend (or, with
`COMPOSE_PROFILES=` and `WEB_MODE=redirect`, runs the API only and redirects browsers to an
externally hosted website), passes the real
client IP (the backend's rate limits depend on it), and serves HTTPS automatically once
`SITE_ADDRESS` is your domain. The API and frontend aren't published directly.

- Paystack webhook: `https://<your-domain>/api/events/webhooks/paystack`
- Uploaded images live in the `uploads` volume (single host). For several hosts use shared
  storage or an object store; see `backend/app/routers/uploads.py`.

## Tests

```bash
cd backend && python -m pytest -q                       # SQLite
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/turnup_test python -m pytest -q
cd frontend && npm run typecheck && npm run build && npm run build:capacitor
```

`scripts/e2e/account_flows.js` drives the account screens in a real browser (instructions in the file).
GitHub Actions (`.github/workflows/ci.yml`) runs all of the above on every push.

## Android app

```bash
cd frontend
npm run build:capacitor       # static export into out/, admin pages removed
npx cap sync android && npx cap open android
npm run cap:live              # live reload from your dev server instead (needs CAPACITOR_DEV_SERVER_URL)
```
