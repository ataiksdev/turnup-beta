from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# ── Request bodies ────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=6, max_length=100)


class LoginRequest(BaseModel):
    identifier: str  # email or username
    password: str


class OnboardingRequest(BaseModel):
    category_preferences: list[str] = Field(min_length=1, max_length=8)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=6, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=100)


class MagicLinkRequest(BaseModel):
    email: EmailStr


class TwoFactorVerifyRequest(BaseModel):
    token: str       # temp token from login
    code: str        # 6-digit TOTP or backup code


class TwoFactorEnableRequest(BaseModel):
    code: str        # verify user has app set up before enabling


class TwoFactorDisableRequest(BaseModel):
    code: str        # TOTP or backup code to confirm identity


class DeleteAccountRequest(BaseModel):
    password: str    # require password confirmation


class PhoneLoginRequest(BaseModel):
    phone_number: str = Field(pattern=r"^\+?[1-9]\d{7,14}$")


class PhoneVerifyRequest(BaseModel):
    phone_number: str = Field(pattern=r"^\+?[1-9]\d{7,14}$")
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class OAuthCompleteRequest(BaseModel):
    partial_token: str
    email: EmailStr


# ── Response bodies ───────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TwoFactorChallenge(BaseModel):
    """Returned from /login when 2FA is enabled."""
    requires_2fa: bool = True
    temp_token: str


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg: str


class TwoFactorEnableResponse(BaseModel):
    backup_codes: list[str]


class SessionOut(BaseModel):
    id: str
    device_name: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_active: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class OAuthProviderRedirect(BaseModel):
    url: str


class OAuthCallbackResponse(BaseModel):
    """Returned from OAuth callback — either a full token or a partial requiring email."""
    access_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    requires_email: bool = False
    partial_token: str | None = None


class MessageResponse(BaseModel):
    message: str
