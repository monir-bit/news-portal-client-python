from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


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
    app_url: str = ""

    db_connection: str = "pgsql"
    db_host: str = "10.68.240.29"
    db_port: int = 5432
    db_database: str = "agamirdb_bangla"
    db_username: str = "agamirdb_bangla"
    db_password: str = "AgamirDB@!Bangla1"

    filesystem_disk: str = "s3"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"
    aws_bucket: str = ""
    aws_endpoint: str = ""
    aws_use_path_style_endpoint: bool = False
    aws_url: str = ""

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.db_username,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_database,
        )

    @property
    def media_base_url(self) -> str:
        if self.aws_url:
            return self.aws_url.rstrip("/")
        if self.aws_use_path_style_endpoint and self.aws_endpoint:
            return f"{self.aws_endpoint.rstrip('/')}/{self.aws_bucket}"
        return self.aws_endpoint.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
