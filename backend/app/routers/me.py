"""Your data: the consent history and "download my data" (app/services/data_rights.py)."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import limiter
from app.models.user import User
from app.services.data_rights import consent_history, export_user_data

router = APIRouter(prefix="/api/me", tags=["me"])


class ConsentOut(BaseModel):
    model_config = {"from_attributes": True}
    setting: str
    value: bool
    source: str
    changed_at: datetime


@router.get("/consents", response_model=list[ConsentOut])
async def my_consents(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await consent_history(db, user.id)


@router.get("/export")
@limiter.limit("5/hour")
async def export_my_data(request: Request, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    data = await export_user_data(db, user)
    name = f"turnup-data-{user.username}-{datetime.now(timezone.utc):%Y%m%d}.json"
    return Response(json.dumps(data, ensure_ascii=False, indent=1, default=str),
                    media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
