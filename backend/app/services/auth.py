import uuid
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _make_jwt(payload: dict, expire_minutes: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    return jwt.encode(
        {**payload, "exp": expire},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def create_access_token(user_id: str, jti: str) -> tuple[str, int]:
    """Returns (token, expires_in_seconds). jti must match a UserSession row."""
    token = _make_jwt({"sub": user_id, "jti": jti, "type": "access"},
                      settings.access_token_expire_minutes)
    return token, settings.access_token_expire_minutes * 60


def create_temp_token(user_id: str) -> str:
    """Short-lived token issued after password-auth when 2FA is required."""
    return _make_jwt({"sub": user_id, "type": "temp"},
                     settings.temp_token_expire_minutes)


def create_partial_oauth_token(provider: str, provider_user_id: str, username: str) -> str:
    """Short-lived token for OAuth flows that need email collection (e.g. Instagram)."""
    return _make_jwt(
        {"sub": provider_user_id, "username": username, "provider": provider, "type": "partial"},
        settings.temp_token_expire_minutes,
    )


def decode_token_full(token: str) -> dict | None:
    """Returns the full JWT payload dict, or None if invalid/expired."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


def decode_token(token: str) -> str | None:
    payload = decode_token_full(token)
    return payload.get("sub") if payload else None


def make_session_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
