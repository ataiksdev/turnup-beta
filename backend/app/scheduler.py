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


async def _run(name: str, fn):
    async with AsyncSessionLocal() as db:
        try:
            result = await fn(db)
            logger.info("%s: %s", name, result)
        except Exception:
            logger.exception("%s failed", name)


async def run_marketplace_frequent():
    """Venue payments/bookings, refund penalties, early alerts (docs/venues-spec.md)."""
    from app.services.alerts import send_due_alerts
    from app.services.venue_booking import run_booking_sweeps
    from app.services.venue_money import run_refund_penalties
    await _run("Venue booking sweeps", run_booking_sweeps)
    await _run("Refund penalties", run_refund_penalties)
    await _run("Scheduled follower alerts", send_due_alerts)


async def run_marketplace_daily():
    from app.services.housekeeping import daily_marketplace
    await _run("Marketplace daily", daily_marketplace)


async def run_offsite_backup():
    from app.services.storage_jobs import offsite_backup
    await _run("Off-server backup", offsite_backup)


async def run_prune_uploads():
    from app.services.storage_jobs import prune_orphan_uploads
    await _run("Unused uploads", prune_orphan_uploads)


async def run_weekend_picks():
    from app.services.picks import send_weekend_picks
    await _run("Weekend picks", send_weekend_picks)


async def run_event_alerts():
    from app.services.nudges import send_event_alerts
    await _run("Saved-event alerts", send_event_alerts)


async def run_search_alerts():
    from app.services.search_alerts import send_search_alerts
    await _run("Search alerts", send_search_alerts)


async def run_rec_event_features():
    from app.services.rec_features import run_event_features
    await _run("Recommendation event features", run_event_features)


async def run_rec_user_features():
    from app.services.rec_features import run_user_features
    await _run("Recommendation user features", run_user_features)


async def run_prune_activity():
    from app.services.activity import prune_old_activity
    await _run("Activity retention", prune_old_activity)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # Ticket-order expiry is core payment hygiene, so it always runs; the scout is added
    # only when an AI provider key is configured.
    scheduler.add_job(
        run_expire_pending_orders, IntervalTrigger(minutes=10),
        id="expire_pending_orders", replace_existing=True,
        max_instances=1, coalesce=True,
    )
    scheduler.add_job(run_marketplace_frequent, IntervalTrigger(minutes=10), id="marketplace_frequent",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(run_marketplace_daily, CronTrigger(hour=2, minute=17), id="marketplace_daily",
                      replace_existing=True, max_instances=1, coalesce=True)
    # Every 6 hours: copies the newest database dump once it exists (the backup service makes
    # one a day), plus that day's KYC archive; skipped unless off-server backups are set up.
    scheduler.add_job(run_offsite_backup, IntervalTrigger(hours=6), id="offsite_backup",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(run_prune_uploads, CronTrigger(day_of_week="sun", hour=3, minute=41), id="prune_uploads",
                      replace_existing=True, max_instances=1, coalesce=True)
    # Thursdays 16:00 Lagos (15:00 UTC).
    scheduler.add_job(run_weekend_picks, CronTrigger(day_of_week="thu", hour=15, minute=7), id="weekend_picks",
                      replace_existing=True, max_instances=1, coalesce=True)
    # "Almost sold out" / "price dropped" for saved events: 10:07 and 18:07 Lagos, never at night.
    scheduler.add_job(run_event_alerts, CronTrigger(hour="9,17", minute=7), id="event_alerts",
                      replace_existing=True, max_instances=1, coalesce=True)
    # "Notify me" searches: hourly, against events created since the last check.
    scheduler.add_job(run_search_alerts, IntervalTrigger(hours=1), id="search_alerts",
                      replace_existing=True, max_instances=1, coalesce=True)
    # Recommendations (docs/recommendations-spec.md): event numbers every 15 minutes, people's
    # nightly (Lagos 04:00), then old activity past its retention period is deleted.
    scheduler.add_job(run_rec_event_features, IntervalTrigger(minutes=15), id="rec_event_features",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(run_rec_user_features, CronTrigger(hour=3, minute=3), id="rec_user_features",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(run_prune_activity, CronTrigger(hour=3, minute=47), id="prune_activity",
                      replace_existing=True, max_instances=1, coalesce=True)
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
