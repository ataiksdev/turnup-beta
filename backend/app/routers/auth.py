import json
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import limiter
from app.models.auth_tokens import (
    EmailVerification, MagicLink, OAuthAccount, PasswordReset, PhoneOTP, TwoFactor, UserSession,
)
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest, DeleteAccountRequest, ForgotPasswordRequest,
    LoginRequest, MagicLinkRequest, MessageResponse, OAuthCallbackResponse,
    OAuthCompleteRequest, OnboardingRequest, OAuthProviderRedirect,
    PhoneLoginRequest, PhoneVerifyRequest,
    RegisterRequest, ResetPasswordRequest,
    SessionOut, Token, TwoFactorChallenge, TwoFactorDisableRequest,
    TwoFactorEnableRequest, TwoFactorEnableResponse,
    TwoFactorSetupResponse, TwoFactorVerifyRequest,
)
from app.schemas.user import UserMe, UserUpdate
from app.services.auth import (
    create_access_token, create_partial_oauth_token, create_temp_token, decode_token_full,
    hash_password, make_session_expiry, verify_password,
)
from app.services.email import (
    send_magic_link_email, send_password_reset_email, send_verification_email,
)
from app.services.sms import send_otp_sms
from app.services.totp import (
    generate_backup_codes, generate_totp_secret, get_qr_svg, get_totp_uri,
    hash_backup_codes, verify_backup_code, verify_totp,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _create_session(
    db: AsyncSession,
    user: User,
    request: Request,
    device_name: str | None = None,
) -> Token:
    jti = str(uuid.uuid4())
    token, expires_in = create_access_token(user.id, jti)
    session = UserSession(
        user_id=user.id,
        jti=jti,
        device_name=device_name or request.headers.get("x-device-name"),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        expires_at=make_session_expiry(),
    )
    db.add(session)
    await db.flush()
    return Token(access_token=token, token_type="bearer", expires_in=expires_in)


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


# ── Register & Login ──────────────────────────────────────────────────────────

@router.post("/register", response_model=Token, status_code=201)
@limiter.limit(settings.rate_limit_register)
async def register(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if await _get_user_by_email(db, payload.email):
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

    # Send verification email
    ev_token = secrets.token_urlsafe(64)
    db.add(EmailVerification(
        user_id=user.id,
        token=ev_token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.email_verify_expire_hours),
    ))
    await db.flush()
    await send_verification_email(user.email, ev_token)

    return await _create_session(db, user, request)


@router.post("/login")
@limiter.limit(settings.rate_limit_login)
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await _get_user_by_email(db, payload.email)
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password")
    if not user.is_active or user.is_deleted:
        raise HTTPException(403, "Account disabled")

    if user.two_factor_enabled:
        return TwoFactorChallenge(temp_token=create_temp_token(user.id))

    return await _create_session(db, user, request)


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from fastapi.security import OAuth2PasswordBearer
    from app.services.auth import decode_token_full as dtf
    # Extract jti from the current bearer token
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    payload = dtf(token)
    if payload and payload.get("jti"):
        await db.execute(
            delete(UserSession).where(UserSession.jti == payload["jti"])
        )
    return MessageResponse(message="Logged out")


# ── Email verification ────────────────────────────────────────────────────────

@router.get("/verify-email", response_model=MessageResponse)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EmailVerification).where(
            EmailVerification.token == token,
            EmailVerification.is_used == False,
            EmailVerification.expires_at > now,
        )
    )
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(400, "Invalid or expired verification token")

    ev.is_used = True
    user_result = await db.execute(select(User).where(User.id == ev.user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.email_verified = True
        user.is_verified = True
    await db.flush()
    return MessageResponse(message="Email verified successfully")


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_resend_verify)
async def resend_verification(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.email_verified:
        raise HTTPException(400, "Email already verified")

    # Invalidate old tokens
    await db.execute(
        delete(EmailVerification).where(EmailVerification.user_id == user.id)
    )
    ev_token = secrets.token_urlsafe(64)
    db.add(EmailVerification(
        user_id=user.id,
        token=ev_token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.email_verify_expire_hours),
    ))
    await db.flush()
    await send_verification_email(user.email, ev_token)
    return MessageResponse(message="Verification email sent")


# ── Password reset ────────────────────────────────────────────────────────────

@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_forgot_password)
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_by_email(db, payload.email)
    # Always return success to prevent email enumeration
    if user and not user.is_deleted:
        await db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
        token = secrets.token_urlsafe(64)
        db.add(PasswordReset(
            user_id=user.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_expire_minutes),
        ))
        await db.flush()
        await send_password_reset_email(user.email, token)
    return MessageResponse(message="If that email exists, a reset link has been sent")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PasswordReset).where(
            PasswordReset.token == payload.token,
            PasswordReset.is_used == False,
            PasswordReset.expires_at > now,
        )
    )
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(400, "Invalid or expired reset token")

    pr.is_used = True
    user_result = await db.execute(select(User).where(User.id == pr.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    user.hashed_password = hash_password(payload.new_password)
    # Revoke all sessions for security
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    await db.flush()
    return MessageResponse(message="Password reset successful. Please log in again.")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.hashed_password or not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(400, "Current password is incorrect")
    user.hashed_password = hash_password(payload.new_password)
    await db.flush()
    return MessageResponse(message="Password changed successfully")


# ── 2FA ───────────────────────────────────────────────────────────────────────

@router.post("/2fa/verify", response_model=Token)
async def verify_2fa(request: Request, payload: TwoFactorVerifyRequest, db: AsyncSession = Depends(get_db)):
    token_payload = decode_token_full(payload.token)
    if not token_payload or token_payload.get("type") != "temp":
        raise HTTPException(401, "Invalid or expired 2FA session")

    user_id = token_payload.get("sub")
    user_result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = user_result.scalar_one_or_none()
    if not user or not user.two_factor_enabled:
        raise HTTPException(401, "Invalid 2FA session")

    tf_result = await db.execute(select(TwoFactor).where(TwoFactor.user_id == user_id))
    tf = tf_result.scalar_one_or_none()
    if not tf:
        raise HTTPException(500, "2FA not configured")

    code = payload.code.strip().upper()
    if verify_totp(tf.secret, code):
        return await _create_session(db, user, request)

    # Try backup code
    if tf.backup_codes:
        codes = json.loads(tf.backup_codes)
        idx = verify_backup_code(code, codes)
        if idx is not None:
            codes.pop(idx)
            tf.backup_codes = json.dumps(codes)
            await db.flush()
            return await _create_session(db, user, request)

    raise HTTPException(401, "Invalid 2FA code")


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_2fa(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.two_factor_enabled:
        raise HTTPException(400, "2FA is already enabled")

    # Remove stale pending setup
    await db.execute(delete(TwoFactor).where(TwoFactor.user_id == user.id))
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, user.email)
    db.add(TwoFactor(user_id=user.id, secret=secret))
    await db.flush()
    return TwoFactorSetupResponse(secret=secret, otpauth_uri=uri, qr_svg=get_qr_svg(uri))


@router.post("/2fa/enable", response_model=TwoFactorEnableResponse)
async def enable_2fa(
    payload: TwoFactorEnableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.two_factor_enabled:
        raise HTTPException(400, "2FA is already enabled")

    tf_result = await db.execute(select(TwoFactor).where(TwoFactor.user_id == user.id))
    tf = tf_result.scalar_one_or_none()
    if not tf:
        raise HTTPException(400, "Run /2fa/setup first")

    if not verify_totp(tf.secret, payload.code):
        raise HTTPException(400, "Invalid TOTP code")

    plain_codes = generate_backup_codes()
    tf.backup_codes = json.dumps(hash_backup_codes(plain_codes))
    user.two_factor_enabled = True
    await db.flush()
    return TwoFactorEnableResponse(backup_codes=plain_codes)


@router.post("/2fa/disable", response_model=MessageResponse)
async def disable_2fa(
    payload: TwoFactorDisableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.two_factor_enabled:
        raise HTTPException(400, "2FA is not enabled")

    tf_result = await db.execute(select(TwoFactor).where(TwoFactor.user_id == user.id))
    tf = tf_result.scalar_one_or_none()

    code = payload.code.strip().upper()
    valid = tf and verify_totp(tf.secret, code)
    if not valid and tf and tf.backup_codes:
        codes = json.loads(tf.backup_codes)
        valid = verify_backup_code(code, codes) is not None

    if not valid:
        raise HTTPException(400, "Invalid code")

    await db.execute(delete(TwoFactor).where(TwoFactor.user_id == user.id))
    user.two_factor_enabled = False
    await db.flush()
    return MessageResponse(message="2FA disabled")


@router.post("/2fa/backup-codes", response_model=TwoFactorEnableResponse)
async def regenerate_backup_codes(
    payload: TwoFactorEnableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify current TOTP code then issue fresh backup codes."""
    if not user.two_factor_enabled:
        raise HTTPException(400, "2FA is not enabled")
    tf_result = await db.execute(select(TwoFactor).where(TwoFactor.user_id == user.id))
    tf = tf_result.scalar_one_or_none()
    if not tf or not verify_totp(tf.secret, payload.code):
        raise HTTPException(400, "Invalid TOTP code")

    plain_codes = generate_backup_codes()
    tf.backup_codes = json.dumps(hash_backup_codes(plain_codes))
    await db.flush()
    return TwoFactorEnableResponse(backup_codes=plain_codes)


# ── Session management ────────────────────────────────────────────────────────

@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.is_active == True,
            UserSession.expires_at > now,
        ).order_by(UserSession.last_active.desc())
    )
    return result.scalars().all()


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def revoke_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")
    session.is_active = False
    await db.flush()
    return MessageResponse(message="Session revoked")


@router.delete("/sessions", response_model=MessageResponse)
async def revoke_all_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all sessions except the current one."""
    auth_header = request.headers.get("authorization", "")
    current_token = auth_header.removeprefix("Bearer ").strip()
    from app.services.auth import decode_token_full as dtf
    payload = dtf(current_token)
    current_jti = payload.get("jti") if payload else None

    q = select(UserSession).where(UserSession.user_id == user.id, UserSession.is_active == True)
    result = await db.execute(q)
    sessions = result.scalars().all()
    for s in sessions:
        if s.jti != current_jti:
            s.is_active = False
    await db.flush()
    return MessageResponse(message=f"Revoked {len(sessions) - 1} other sessions")


# ── Account deletion ──────────────────────────────────────────────────────────

@router.delete("/account", response_model=MessageResponse)
async def delete_account(
    payload: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(400, "Incorrect password")

    user.is_deleted = True
    user.is_active = False
    user.deleted_at = datetime.now(timezone.utc)
    # Revoke all sessions
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    await db.flush()
    return MessageResponse(message="Account scheduled for deletion")


# ── Magic link ────────────────────────────────────────────────────────────────

@router.post("/magic-link", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_magic_link)
async def request_magic_link(
    request: Request,
    payload: MagicLinkRequest,
    db: AsyncSession = Depends(get_db),
):
    # Invalidate old magic links for this email
    await db.execute(delete(MagicLink).where(MagicLink.email == payload.email))
    token = secrets.token_urlsafe(64)
    db.add(MagicLink(
        email=payload.email,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.magic_link_expire_minutes),
    ))
    await db.flush()
    await send_magic_link_email(payload.email, token)
    return MessageResponse(message="Magic link sent if the email is registered")


@router.get("/magic-link/verify", response_model=Token)
async def verify_magic_link(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(MagicLink).where(
            MagicLink.token == token,
            MagicLink.is_used == False,
            MagicLink.expires_at > now,
        )
    )
    ml = result.scalar_one_or_none()
    if not ml:
        raise HTTPException(400, "Invalid or expired magic link")

    ml.is_used = True
    user = await _get_user_by_email(db, ml.email)
    if not user or user.is_deleted:
        raise HTTPException(404, "No account for this email")
    if not user.is_active:
        raise HTTPException(403, "Account disabled")

    # Auto-verify email via magic link
    if not user.email_verified:
        user.email_verified = True
        user.is_verified = True

    await db.flush()
    return await _create_session(db, user, request, device_name="Magic Link")


# ── OAuth ─────────────────────────────────────────────────────────────────────

_OAUTH_CONFIGS = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
        "scope": "openid email profile",
        "client_id": lambda: settings.google_client_id,
        "client_secret": lambda: settings.google_client_secret,
        "userinfo_auth": "bearer",
    },
    "instagram": {
        "auth_url": "https://api.instagram.com/oauth/authorize",
        "token_url": "https://api.instagram.com/oauth/access_token",
        "userinfo_url": "https://graph.instagram.com/me",
        "scope": "user_profile,user_media",
        "client_id": lambda: settings.instagram_client_id,
        "client_secret": lambda: settings.instagram_client_secret,
        "userinfo_auth": "query",          # token passed as ?access_token=
        "userinfo_params": {"fields": "id,username"},
    },
}


def _oauth_redirect_uri(provider: str) -> str:
    return f"{settings.frontend_url}/auth/oauth/{provider}/callback"


@router.get("/oauth/{provider}", response_model=OAuthProviderRedirect)
async def oauth_redirect(provider: str):
    cfg = _OAUTH_CONFIGS.get(provider)
    if not cfg:
        raise HTTPException(400, f"Unknown provider: {provider}")

    client_id = cfg["client_id"]()
    if not client_id:
        raise HTTPException(503, f"{provider} OAuth not configured")

    state = secrets.token_urlsafe(16)
    params = {
        "client_id": client_id,
        "redirect_uri": _oauth_redirect_uri(provider),
        "scope": cfg["scope"],
        "response_type": "code",
        "state": state,
    }
    import urllib.parse
    url = cfg["auth_url"] + "?" + urllib.parse.urlencode(params)
    return OAuthProviderRedirect(url=url)


@router.get("/oauth/{provider}/callback", response_model=OAuthCallbackResponse)
async def oauth_callback(
    provider: str,
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    state: str | None = None,
):
    cfg = _OAUTH_CONFIGS.get(provider)
    if not cfg:
        raise HTTPException(400, f"Unknown provider: {provider}")

    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_params = {
            "client_id": cfg["client_id"](),
            "client_secret": cfg["client_secret"](),
            "code": code,
            "redirect_uri": _oauth_redirect_uri(provider),
            "grant_type": "authorization_code",
        }
        tr = await client.post(cfg["token_url"], data=token_params, headers={"Accept": "application/json"})
        tr.raise_for_status()
        token_data = tr.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(400, "Failed to obtain access token from provider")

        # Fetch user info — Instagram uses query param auth, others use Bearer
        extra_params = {**cfg.get("userinfo_params", {})}
        if cfg.get("userinfo_auth") == "query":
            extra_params["access_token"] = access_token
            ur = await client.get(cfg["userinfo_url"], params=extra_params,
                                  headers={"Accept": "application/json"})
        else:
            ur = await client.get(
                cfg["userinfo_url"],
                params=extra_params or None,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
        ur.raise_for_status()
        userinfo = ur.json()

    provider_user_id = str(userinfo.get("sub") or userinfo.get("id", ""))
    email = userinfo.get("email")
    name = userinfo.get("name") or userinfo.get("username") or (email.split("@")[0] if email else "user")

    # Check for existing OAuth account link (works even without email)
    oa_result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id,
        )
    )
    oa = oa_result.scalar_one_or_none()

    if oa:
        # Returning user — update token and log in
        oa.access_token = access_token
        user_result = await db.execute(select(User).where(User.id == oa.user_id))
        user = user_result.scalar_one()
        await db.flush()
        token = await _create_session(db, user, request, device_name=f"{provider.title()} OAuth")
        return OAuthCallbackResponse(
            access_token=token.access_token,
            token_type=token.token_type,
            expires_in=token.expires_in,
        )

    # New OAuth account
    if not email:
        # Instagram (and any provider without email): return partial token for email collection
        username_candidate = (userinfo.get("username") or f"user{provider_user_id[-6:]}").lower()
        username_candidate = "".join(c for c in username_candidate if c.isalnum() or c == "_")[:30]
        partial = create_partial_oauth_token(provider, provider_user_id, username_candidate)
        return OAuthCallbackResponse(requires_email=True, partial_token=partial)

    # Provider returned email — find or create user
    user = await _get_user_by_email(db, email)
    if not user:
        username_base = name.lower().replace(" ", "_")
        username_base = "".join(c for c in username_base if c.isalnum() or c == "_")[:30] or "user"
        username = username_base
        suffix = 1
        while (await db.execute(select(User).where(User.username == username))).scalar_one_or_none():
            username = f"{username_base}{suffix}"
            suffix += 1

        user = User(
            id=str(uuid.uuid4()),
            email=email,
            username=username,
            full_name=name,
            email_verified=True,
            is_verified=True,
        )
        db.add(user)
        await db.flush()

    db.add(OAuthAccount(
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
        provider_email=email,
        access_token=access_token,
    ))
    await db.flush()
    token = await _create_session(db, user, request, device_name=f"{provider.title()} OAuth")
    return OAuthCallbackResponse(
        access_token=token.access_token,
        token_type=token.token_type,
        expires_in=token.expires_in,
    )


@router.post("/oauth/complete", response_model=Token)
async def oauth_complete(
    payload: OAuthCompleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Complete OAuth signup for providers that don't return email (e.g. Instagram)."""
    token_payload = decode_token_full(payload.partial_token)
    if not token_payload or token_payload.get("type") != "partial":
        raise HTTPException(401, "Invalid or expired partial token")

    provider = token_payload["provider"]
    provider_user_id = token_payload["sub"]
    username_hint = token_payload.get("username", "")

    # Check the OAuth account wasn't linked in the meantime
    oa_result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id,
        )
    )
    if oa_result.scalar_one_or_none():
        raise HTTPException(400, "Account already linked")

    # Find or create user by email
    user = await _get_user_by_email(db, payload.email)
    if not user:
        username_base = username_hint or payload.email.split("@")[0].lower()
        username_base = "".join(c for c in username_base if c.isalnum() or c == "_")[:30] or "user"
        username = username_base
        suffix = 1
        while (await db.execute(select(User).where(User.username == username))).scalar_one_or_none():
            username = f"{username_base}{suffix}"
            suffix += 1

        user = User(
            id=str(uuid.uuid4()),
            email=payload.email,
            username=username,
            full_name=username_hint or payload.email.split("@")[0],
            email_verified=True,
            is_verified=True,
        )
        db.add(user)
        await db.flush()

    db.add(OAuthAccount(
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
        provider_email=payload.email,
    ))
    await db.flush()
    return await _create_session(db, user, request, device_name=f"{provider.title()} OAuth")


# ── Phone OTP ─────────────────────────────────────────────────────────────────

@router.post("/phone/send-otp", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_phone_otp)
async def phone_send_otp(
    request: Request,
    payload: PhoneLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    # Invalidate old OTPs for this number
    await db.execute(delete(PhoneOTP).where(PhoneOTP.phone_number == payload.phone_number))
    otp_code = str(random.randint(100000, 999999))
    db.add(PhoneOTP(
        phone_number=payload.phone_number,
        otp_code=otp_code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expiry_minutes),
    ))
    await db.flush()
    await send_otp_sms(payload.phone_number, otp_code)
    return MessageResponse(message="OTP sent")


@router.post("/phone/verify", response_model=Token)
@limiter.limit(settings.rate_limit_phone_verify)
async def phone_verify(
    request: Request,
    payload: PhoneVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PhoneOTP).where(
            PhoneOTP.phone_number == payload.phone_number,
            PhoneOTP.is_used == False,
            PhoneOTP.expires_at > now,
        ).order_by(PhoneOTP.created_at.desc())
    )
    otp = result.scalar_one_or_none()
    if not otp:
        raise HTTPException(400, "No active OTP for this number. Request a new one.")

    otp.attempts += 1
    if otp.attempts > 3:
        await db.flush()
        raise HTTPException(400, "Too many attempts. Request a new OTP.")

    if otp.otp_code != payload.otp_code:
        await db.flush()
        raise HTTPException(400, "Invalid OTP code")

    otp.is_used = True

    # Find or create user by phone number
    user_result = await db.execute(select(User).where(User.phone_number == payload.phone_number))
    user = user_result.scalar_one_or_none()

    if not user:
        base = f"user{payload.phone_number.replace('+', '')[-6:]}"
        username = base
        suffix = 1
        while (await db.execute(select(User).where(User.username == username))).scalar_one_or_none():
            username = f"{base}{suffix}"
            suffix += 1
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            phone_number=payload.phone_number,
            is_verified=True,
        )
        db.add(user)
    elif user.is_deleted or not user.is_active:
        raise HTTPException(403, "Account disabled")

    await db.flush()
    return await _create_session(db, user, request, device_name="Phone OTP")


# ── Profile endpoints ─────────────────────────────────────────────────────────

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
