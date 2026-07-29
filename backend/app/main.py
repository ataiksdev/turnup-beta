import logging
import os
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.database import AsyncSessionLocal, init_db
from app.middleware.rate_limit import limiter
from app.routers import auth, events, social, users
from app.routers import organizer
from app.routers import series
from app.routers import admin
from app.routers import communities

os.makedirs("data", exist_ok=True)
logger = logging.getLogger("turnup.scout")


async def _run_scheduled_scout():
    from app.services.scout_agent import run_daily_scout
    async with AsyncSessionLocal() as db:
        try:
            summary = await run_daily_scout(db)
            logger.info("Daily scout run complete: %s", summary)
        except Exception:
            logger.exception("Daily scout run failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    scheduler = None
    if settings.ai_provider_api_key:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            _run_scheduled_scout,
            CronTrigger(hour=settings.scout_hour_utc, minute=0),
            id="daily_scout",
            replace_existing=True,
        )
        scheduler.start()
    else:
        logger.warning(
            "No API key set for AI_PROVIDER=%s — daily scout agent is disabled.",
            settings.ai_provider,
        )

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


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.app_version}
