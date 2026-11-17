from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://english_reps:local-only@localhost:5432/english_reps"
    allowed_origins: list[str] = ["http://localhost:3007", "http://localhost:8080"]
    cookie_secure: bool = False
    session_days: int = Field(default=14, ge=1, le=90)
    auth_limit: int = Field(default=20, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        if not self.database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        if not self.allowed_origins:
            raise ValueError("At least one ALLOWED_ORIGINS entry is required")
        for origin in self.allowed_origins:
            parts = urlsplit(origin)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.netloc
                or parts.path
                or parts.query
                or parts.fragment
            ):
                raise ValueError("ALLOWED_ORIGINS must contain exact HTTP origins")
            if self.app_env == "production" and parts.scheme != "https":
                raise ValueError("Production origins require HTTPS")
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("Production cookies must be Secure")
        return self

    @property
    def session_cookie(self) -> str:
        return "__Host-er_session" if self.cookie_secure else "er_session"

    @property
    def csrf_cookie(self) -> str:
        return "__Host-er_csrf" if self.cookie_secure else "er_csrf"


@lru_cache
def get_settings() -> Settings:
    return Settings()
