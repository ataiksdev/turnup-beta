"""
Users service — aggregates data from auth-service and events-service.
No own database needed: it orchestrates calls to other services.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import httpx

from app.config import settings

router = APIRouter()
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _get_uid(token: str | None = Depends(oauth2)) -> str:
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])["sub"]
    except (JWTError, KeyError):
        raise HTTPException(401, "Invalid token")


def _get_optional_uid(token: str | None = Depends(oauth2)) -> str | None:
    if not token:
        return None
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm]).get("sub")
    except JWTError:
        return None


async def _auth(path: str):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{settings.auth_service_url}{path}", timeout=5)
        if r.status_code == 404:
            raise HTTPException(404, "User not found")
        r.raise_for_status()
        return r.json()


async def _events(path: str):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{settings.events_service_url}{path}", timeout=5)
        r.raise_for_status()
        return r.json()


async def _social(path: str):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{settings.social_service_url}{path}", timeout=5)
        r.raise_for_status()
        return r.json()


@router.get("/users/{username}")
async def get_user_profile(username: str, uid: str | None = Depends(_get_optional_uid)):
    user = await _auth(f"/internal/users/by-username/{username}")

    # Check if the current user follows this user
    is_following = False
    if uid and uid != user["id"]:
        try:
            follow_data = await _social(f"/internal/follows/{uid}/{user['id']}")
            is_following = follow_data.get("is_following", False)
        except Exception:
            pass

    return {**user, "is_following": is_following}


@router.get("/users/{username}/events")
async def get_user_events(username: str, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50)):
    user = await _auth(f"/internal/users/by-username/{username}")
    return await _events(f"/internal/events/by-host/{user['id']}?page={page}&limit={limit}")


@router.get("/users/{username}/saved")
async def get_saved_events(username: str, page: int = Query(1, ge=1),
                            limit: int = Query(20, ge=1, le=50), uid: str = Depends(_get_uid)):
    user = await _auth(f"/internal/users/by-username/{username}")
    if uid != user["id"]:
        raise HTTPException(403, "Access denied")
    return await _events(f"/internal/events/saved-by/{uid}?page={page}&limit={limit}")


@router.get("/users/{username}/followers")
async def get_followers(username: str, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50)):
    user = await _auth(f"/internal/users/by-username/{username}")
    return await _social(f"/internal/followers/{user['id']}?page={page}&limit={limit}")


@router.get("/users/{username}/following")
async def get_following(username: str, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50)):
    user = await _auth(f"/internal/users/by-username/{username}")
    return await _social(f"/internal/following/{user['id']}?page={page}&limit={limit}")
