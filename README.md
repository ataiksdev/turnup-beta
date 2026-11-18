# Turnup

Event discovery and ticketing: find events, RSVP, buy tickets (Paystack), check in at the
door, run events as an organizer, and moderate as an admin. Ships as a website and an
Android app (Capacitor).

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

Optional sample data: `python scripts/seed.py`.

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

## Deploying with Docker

```bash
cp .env.example .env          # set SECRET_KEY, POSTGRES_PASSWORD, Paystack/SMTP keys
docker compose up -d --build
```

This starts Postgres, a one-off `migrate` job, the API (2 workers, no jobs), a single
`worker`, and the frontend on port 3000. The API is not published. Browsers and Paystack
webhooks reach it through the frontend's `/api` proxy, so point the Paystack webhook at
`https://<your-site>/api/events/webhooks/paystack`.

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
```
