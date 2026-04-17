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

    # OAuth — GitHub
    github_client_id: str = ""
    github_client_secret: str = ""

    # Rate limiting
    rate_limit_login: str = "5/minute"
    rate_limit_register: str = "3/minute"
    rate_limit_forgot_password: str = "3/minute"
    rate_limit_resend_verify: str = "2/minute"
    rate_limit_magic_link: str = "3/minute"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
