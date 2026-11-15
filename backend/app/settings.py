"""Configuration from environment variables (and a local, git-ignored .env)."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+psycopg://cic:cic@localhost:5432/cic"
    app_env: Literal["dev", "test", "prod"] = "dev"
    # Secure cookies need HTTPS; browsers also accept them on http://localhost.
    cookie_secure: bool = True
    session_idle_hours: int = 12
    session_absolute_days: int = 7
    messaging_mode: Literal["dry_run", "live"] = "dry_run"
    # Resend, used only when messaging_mode is "live". Never logged or stored.
    resend_api_key: SecretStr = SecretStr("")
    mail_from: str = ""
    demo_mode: bool = False
    # Directory with the built SPA (frontend/dist). Served by FastAPI when present.
    static_dir: str = "../frontend/dist"
    timezone: str = "America/Phoenix"

    @property
    def sqlalchemy_url(self) -> str:
        """Accept plain postgres:// URLs (Neon, Render) and use the psycopg 3 driver."""
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
