from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    database_url: str = "sqlite+aiosqlite:///./data/social.db"
    secret_key: str = "changeme-dev-key-not-for-production"
    algorithm: str = "HS256"
    auth_service_url: str = "http://localhost:8001"
    events_service_url: str = "http://localhost:8002"
    service_port: int = 8004
    debug: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
