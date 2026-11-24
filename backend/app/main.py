import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.database import init_db
from app.middleware.rate_limit import limiter
from app.routers import auth, events, social, users
from app.routers import organizer
from app.routers import series
from app.routers import admin
from app.routers import communities
from app.routers import uploads
from app.routers import discovery, me, share
from app.routers import admin_venues, agents, plus, venue_bookings, venue_portal, venues
from app.routers import track

os.makedirs("data", exist_ok=True)
logger = logging.getLogger("turnup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Defaults suit local dev (one process does everything). Production (docker-compose)
    # migrates once via `python -m app.cli migrate` and runs jobs in `python -m app.worker`.
    if settings.run_migrations_on_startup:
        await init_db()

    scheduler = None
    if settings.run_scheduler:
        from app.scheduler import build_scheduler
        scheduler = build_scheduler()
        scheduler.start()

    yield

    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Turnup — Event discovery platform API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(events.router)
app.include_router(users.router)
app.include_router(social.router)
app.include_router(organizer.router)
app.include_router(series.router)
app.include_router(admin.router)
app.include_router(communities.router)
app.include_router(uploads.router)
app.include_router(venues.router)
app.include_router(venue_portal.router)
app.include_router(venue_bookings.router)
app.include_router(agents.router)
app.include_router(admin_venues.router)
app.include_router(plus.router)
app.include_router(discovery.router)
app.include_router(share.router)
app.include_router(me.router)
app.include_router(track.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.app_version}
