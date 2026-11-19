"""Daily marketplace housekeeping: subscriptions, featured slots, KYC retention, Wrapped."""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.venue import FeaturedSlot, VenueDocument
from app.services import kyc_store
from app.services.plus import expire_lapsed


async def daily_marketplace(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    out = {"subscriptions_lapsed": await expire_lapsed(db)}
    ended = await db.execute(update(FeaturedSlot).where(
        FeaturedSlot.status == "active", FeaturedSlot.ends_at < now).values(status="ended"))
    out["featured_ended"] = ended.rowcount
    # KYC retention (docs/venues-spec.md 8.2): files are deleted once delete_after passes.
    docs = (await db.execute(select(VenueDocument).where(
        VenueDocument.delete_after.is_not(None), VenueDocument.delete_after < now))).scalars().all()
    for d in docs:
        kyc_store.delete(d.storage_key)
        await db.delete(d)
    out["kyc_deleted"] = len(docs)
    await db.commit()
    if now.month == 12:
        from app.services.wrapped import announce_wrapped
        out["wrapped_announced"] = await announce_wrapped(db, now.year)
    return out
