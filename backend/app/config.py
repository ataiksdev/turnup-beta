from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "changeme"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    app_name: str = "Turnup"
    app_version: str = "1.0.0"
    debug: bool = True
    sql_echo: bool = False  # log every SQL statement (very noisy; was tied to DEBUG)
    # Process roles (see app/scheduler.py and docker-compose.yml). Both default to true so a
    # single `uvicorn app.main:app` works for local dev.
    run_migrations_on_startup: bool = True
    run_scheduler: bool = True
    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Uploaded images (see app/routers/uploads.py). PUBLIC_BASE_URL is the public origin that
    # serves /api/* (defaults to FRONTEND_URL, since the frontend proxies /api to the backend).
    upload_dir: str = "data/uploads"
    public_base_url: str = ""
    # Venue verification documents (CAC, IDs, agent visit photos). Private: never served by
    # /api/uploads; only through short-lived signed links after an access check. Keep it on
    # its own volume (docker-compose.yml) and out of public backups.
    kyc_dir: str = "data/kyc"
    venue_video_max_mb: int = 100
    venue_video_max_seconds: int = 60

    # Object storage (any S3-compatible service: Cloudflare R2, Supabase Storage, AWS S3,
    # Backblaze B2...). See app/services/storage.py and deploy/oracle/README.md.
    # STORAGE_BACKEND=local keeps public uploads on disk (UPLOAD_DIR); "s3" puts them in
    # S3_BUCKET and links to S3_PUBLIC_BASE_URL (the bucket's public address).
    storage_backend: str = "local"
    s3_endpoint_url: str = ""
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = ""
    s3_public_base_url: str = ""
    # Off-server backups: the nightly database dump and the KYC files, encrypted with
    # BACKUP_PASSPHRASE, copied to BACKUP_S3_BUCKET (a PRIVATE bucket, same credentials).
    backup_s3_bucket: str = ""
    backup_passphrase: str = ""
    backup_dir: str = "/backups"
    offsite_keep_days: int = 30
    # Unused public uploads older than this are deleted by the weekly cleanup.
    orphan_upload_grace_days: int = 7

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/turnup.db"

    # JWT
    secret_key: str = DEFAULT_SECRET_KEY
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
    pending_order_expiry_minutes: int = 30  # abandoned pending ticket orders auto-cancel after this long

    # AI event-drafting agent — pluggable provider (used by both the manual AI Draft
    # screen and the daily scout agent). Set ai_provider to whichever key you have.
    ai_provider: str = "anthropic"  # anthropic | openai | gemini

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    # Daily scout agent — polls public RSS/Atom feeds and drafts pending events
    scout_bot_username: str = "ai_scout"
    scout_hour_utc: int = 6            # 0-23, UTC hour the daily run fires
    scout_max_items_per_run: int = 20  # cap on Anthropic calls per run, across all sources
    scout_max_links_per_source: int = 25  # cap on candidate links pulled from one source per poll

    # Rate limiting
    rate_limit_login: str = "5/minute"
    rate_limit_register: str = "3/minute"
    rate_limit_forgot_password: str = "3/minute"
    rate_limit_resend_verify: str = "2/minute"
    rate_limit_magic_link: str = "3/minute"
    rate_limit_phone_otp: str = "3/minute"
    rate_limit_phone_verify: str = "5/minute"
    rate_limit_2fa_verify: str = "5/minute"
    rate_limit_upload: str = "20/minute"
    rate_limit_checkout: str = "10/minute"
    rate_limit_refund: str = "10/minute"
    rate_limit_checkin: str = "60/minute"    # high-volume door scanning at event entry
    rate_limit_comment: str = "20/minute"
    rate_limit_review: str = "10/minute"
    rate_limit_follow: str = "30/minute"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def ai_provider_api_key(self) -> str:
        return {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
        }.get(self.ai_provider, "")

    @model_validator(mode="after")
    def _forbid_default_secret_outside_debug(self) -> "Settings":
        if not self.debug and self.secret_key == DEFAULT_SECRET_KEY:
            raise RuntimeError(
                "SECRET_KEY is still the default 'changeme' value while DEBUG=False. "
                "Refusing to start: anyone who knows this default could forge a valid "
                "auth token for any user, including admins. Set a real SECRET_KEY in "
                "the environment before running outside debug mode."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
