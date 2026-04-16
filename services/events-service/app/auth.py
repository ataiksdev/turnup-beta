"""JWT validation — self-contained, no call to auth-service needed."""
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.config import settings

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_user_id(token: str | None = Depends(oauth2)) -> str:
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        uid = payload.get("sub")
        if not uid:
            raise HTTPException(401, "Invalid token")
        return uid
    except JWTError:
        raise HTTPException(401, "Invalid token")


def get_optional_user_id(token: str | None = Depends(oauth2)) -> str | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload.get("sub")
    except JWTError:
        return None
