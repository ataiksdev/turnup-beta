"""Dedicated background-job process: `python -m app.worker`.

Runs the scheduler (see app/scheduler.py) and nothing else, so the API can scale to many
workers/replicas without running every job once per process."""
import asyncio
import logging
import signal

from app.scheduler import build_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("turnup.worker")


async def main() -> None:
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("Worker started with jobs: %s", [j.id for j in scheduler.get_jobs()])
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    scheduler.shutdown(wait=True)
    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
