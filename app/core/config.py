from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# This project's OWN .env, at the fastapi-project/ root — NOT read directly
# from the Laravel app's .env. Copy values over manually (see .env.example)
# when the Laravel side's credentials change; the two are intentionally
# decoupled so this project can point at a different DB/bucket without
# touching (or being silently affected by) the Laravel app's config.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "News Portal API (FastAPI port)"
    app_env: str = "local"
    app_timezone: str = "Asia/Dhaka"

    # Same names as the Laravel .env so both apps share one source of truth.
    db_connection: str = "pgsql"
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_database: str = "agamir_somoy"
    db_username: str = "postgres"
    db_password: str = ""

    # Media URL resolution: mirrors UtilsHelper::GetMediaUrl(), which resolves
    # relative storage paths against config('filesystems.default')'s public URL.
    # Laravel's default disk is `r2`, whose public URL is R2_PUBLIC_URL.
    filesystem_disk: str = "r2"
    r2_public_url: str = ""
    r2_endpoint: str = ""
    r2_bucket: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_database}"
        )

    @property
    def media_base_url(self) -> str:
        return self.r2_public_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
