"""Background jobs: expiring abandoned ticket orders and the daily AI scout.

Exactly ONE process should run these. With several API workers/replicas each would run
every job (duplicate scout runs and AI spend, competing order sweeps), so production runs
them in a dedicated worker (`python -m app.worker`, see docker-compose.yml) and sets
RUN_SCHEDULER=false on the API. Local dev keeps the default (true): one uvicorn process
does everything.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import AsyncSessionLocal

logger = logging.getLogger("turnup.scheduler")


async def run_scheduled_scout():
    from app.services.scout_agent import run_daily_scout
    async with AsyncSessionLocal() as db:
        try:
            summary = await run_daily_scout(db)
            logger.info("Daily scout run complete: %s", summary)
        except Exception:
            logger.exception("Daily scout run failed")


async def run_expire_pending_orders():
    from app.services.tickets import run_expire_pending_orders as sweep
    async with AsyncSessionLocal() as db:
        try:
            summary = await sweep(db, settings.pending_order_expiry_minutes)
            logger.info("Pending-order expiry sweep: %s", summary)
        except Exception:
            logger.exception("Pending-order expiry sweep failed")


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # Ticket-order expiry is core payment hygiene, so it always runs; the scout is added
    # only when an AI provider key is configured.
    scheduler.add_job(
        run_expire_pending_orders, IntervalTrigger(minutes=10),
        id="expire_pending_orders", replace_existing=True,
        max_instances=1, coalesce=True,
    )
    if settings.ai_provider_api_key:
        scheduler.add_job(
            run_scheduled_scout, CronTrigger(hour=settings.scout_hour_utc, minute=0),
            id="daily_scout", replace_existing=True,
            max_instances=1, coalesce=True,
        )
    else:
        logger.warning("No API key set for AI_PROVIDER=%s: daily scout agent is disabled.",
                       settings.ai_provider)
    return scheduler
