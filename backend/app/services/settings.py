from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import PLATFORM_SETTINGS_ID, PlatformSettings


async def get_platform_settings(db: AsyncSession) -> PlatformSettings:
    """Get-or-create the singleton settings row. Lazy creation (rather than relying
    solely on init_db's seeding) keeps this safe to call from tests and any code path
    that runs against a fresh DB without having gone through the app's lifespan."""
    row = (await db.execute(
        select(PlatformSettings).where(PlatformSettings.id == PLATFORM_SETTINGS_ID)
    )).scalar_one_or_none()
    if row:
        return row
    row = PlatformSettings(id=PLATFORM_SETTINGS_ID)
    db.add(row)
    await db.flush()
    return row


async def set_ticket_fee_percent(db: AsyncSession, percent: float) -> PlatformSettings:
    row = await get_platform_settings(db)
    row.ticket_fee_percent = percent
    await db.flush()
    return row
