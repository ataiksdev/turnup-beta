from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    database_url: str = "sqlite+aiosqlite:///./data/auth.db"
    secret_key: str = "changeme-dev-key-not-for-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days
    service_port: int = 8001
    debug: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
