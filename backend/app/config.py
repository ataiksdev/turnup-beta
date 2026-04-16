from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_name: str = "Turnup"
    app_version: str = "0.1.0"
    debug: bool = True

    # Database
    database_url: str = "sqlite+aiosqlite:///./turnup.db"

    # Auth / JWT
    secret_key: str = "changeme"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080   # 7 days
    refresh_token_expire_days: int = 30

    # CORS
    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
