from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    app_name: str = "Turnup"
    app_version: str = "1.0.0"
    debug: bool = True
    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/turnup.db"

    # JWT
    secret_key: str = "changeme"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080       # 7 days
    temp_token_expire_minutes: int = 10            # 2FA pending token
    magic_link_expire_minutes: int = 15
    password_reset_expire_minutes: int = 60
    email_verify_expire_hours: int = 24

    # Email
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@turnup.app"
    smtp_tls: bool = True
    email_console: bool = True   # dev mode: print instead of send

    # OAuth — Google
    google_client_id: str = ""
    google_client_secret: str = ""

    # OAuth — Instagram
    instagram_client_id: str = ""
    instagram_client_secret: str = ""

    # SMS — Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    otp_expiry_minutes: int = 10

    # Payments — Paystack
    paystack_secret_key: str = ""
    paystack_public_key: str = ""

    # AI event-drafting agent — Anthropic
    anthropic_api_key: str = ""
    ai_agent_model: str = "claude-sonnet-5"

    # Daily scout agent — polls public RSS/Atom feeds and drafts pending events
    scout_bot_username: str = "ai_scout"
    scout_hour_utc: int = 6            # 0-23, UTC hour the daily run fires
    scout_max_items_per_run: int = 20  # cap on Anthropic calls per run, across all sources

    # Rate limiting
    rate_limit_login: str = "5/minute"
    rate_limit_register: str = "3/minute"
    rate_limit_forgot_password: str = "3/minute"
    rate_limit_resend_verify: str = "2/minute"
    rate_limit_magic_link: str = "3/minute"
    rate_limit_phone_otp: str = "3/minute"
    rate_limit_phone_verify: str = "5/minute"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
