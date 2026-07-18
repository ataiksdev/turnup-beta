from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.auth_tokens import UserSession
from app.models.user import User
from app.services.auth import decode_token_full

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def _resolve_user(token: str | None, db: AsyncSession) -> User | None:
    if not token:
        return None
    payload = decode_token_full(token)
    if not payload or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id or not jti:
        return None

    now = datetime.now(timezone.utc)
    session_q = await db.execute(
        select(UserSession).where(
            UserSession.jti == jti,
            UserSession.is_active == True,
            UserSession.expires_at > now,
        )
    )
    if not session_q.scalar_one_or_none():
        return None

    result = await db.execute(
        select(User)
        .options(selectinload(User.organizer_profile))
        .where(User.id == user_id, User.is_active == True, User.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def get_current_user(
    token: str | None = Depends(oauth2),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _resolve_user(token, db)
    if not user:
        raise HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    return user


async def get_optional_user(
    token: str | None = Depends(oauth2),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    return await _resolve_user(token, db)


async def get_current_organizer(user: User = Depends(get_current_user)) -> User:
    """Requires the authenticated user to have the organizer role."""
    if user.role != "organizer":
        raise HTTPException(403, "Organizer account required. Use POST /api/organizer/become to upgrade.")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Requires the authenticated user to have the admin role."""
    if user.role != "admin":
        raise HTTPException(403, "Admin access required.")
    return user
