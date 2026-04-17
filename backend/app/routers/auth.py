import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, OnboardingRequest, RegisterRequest, Token
from app.schemas.user import UserMe, UserUpdate
from app.services.auth import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=201)
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


@router.post("/login", response_model=Token)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password")
    token, expires_in = create_access_token(user.id)
    return Token(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserMe)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserMe)
async def update_me(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(user, field, val)
    await db.flush()
    return user


@router.post("/onboarding", response_model=UserMe)
async def complete_onboarding(
    payload: OnboardingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.category_preferences = ",".join(payload.category_preferences)
    user.onboarding_completed = True
    await db.flush()
    return user
