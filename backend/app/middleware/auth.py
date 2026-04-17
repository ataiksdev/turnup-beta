from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.services.auth import decode_token

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2),
    db: AsyncSession = Depends(get_db),
) -> User:
    exc = HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    if not token:
        raise exc
    user_id = decode_token(token)
    if not user_id:
        raise exc
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise exc
    return user


async def get_optional_user(
    token: str | None = Depends(oauth2),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not token:
        return None
    user_id = decode_token(token)
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    return result.scalar_one_or_none()
