import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.schemas import (LoginRequest, OnboardingRequest, OnboardingResponse,
                         RegisterRequest, Token, UserInternal, UserMe, UserUpdate)
from app.security import create_access_token, decode_token, hash_password, verify_password

router = APIRouter()
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def _get_current_user(token: str | None = Depends(oauth2), db: AsyncSession = Depends(get_db)) -> User:
    exc = HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
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


@router.post("/auth/register", response_model=Token, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none():
        raise HTTPException(400, "Email already registered")
    if (await db.execute(select(User).where(User.username == payload.username.lower()))).scalar_one_or_none():
        raise HTTPException(400, "Username already taken")

    user = User(
        id=str(uuid.uuid4()),
        email=payload.email,
        username=payload.username.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.flush()
    token, expires_in = create_access_token(user.id)
    return Token(access_token=token, expires_in=expires_in)


@router.post("/auth/login", response_model=Token)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password")
    token, expires_in = create_access_token(user.id)
    return Token(access_token=token, expires_in=expires_in)


@router.get("/auth/me", response_model=UserMe)
async def get_me(user: User = Depends(_get_current_user)):
    return user


@router.patch("/auth/me", response_model=UserMe)
async def update_me(payload: UserUpdate, user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(user, field, val)
    await db.flush()
    return user


# ── Internal endpoints (called by other services) ──────────────────────────────

@router.post("/auth/onboarding", response_model=OnboardingResponse)
async def complete_onboarding(
    payload: OnboardingRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Called after registration: user selects their category preferences."""
    user.category_preferences = ",".join(payload.category_preferences)
    user.onboarding_completed = True
    await db.flush()
    return OnboardingResponse(
        onboarding_completed=True,
        category_preferences=user.category_preferences,
    )


@router.get("/internal/users/{user_id}", response_model=UserInternal)
async def get_user_internal(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.get("/internal/users/by-username/{username}", response_model=UserInternal)
async def get_user_by_username_internal(username: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.post("/internal/users/{user_id}/increment")
async def increment_user_counter(
    user_id: str,
    field: str,
    amount: int = 1,
    db: AsyncSession = Depends(get_db),
):
    col = getattr(User, field, None)
    if col is None:
        raise HTTPException(400, f"Unknown field: {field}")
    await db.execute(update(User).where(User.id == user_id).values({field: col + amount}))
    return {"ok": True}
