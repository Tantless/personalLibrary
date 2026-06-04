from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PKCS_", env_file=".env", extra="ignore")

    app_name: str = "Personal Knowledge Context Server"
    env: str = "local"
    http_host: str = "127.0.0.1"
    http_port: int = 8765
    database_url: str = "postgresql+psycopg://pkcs:pkcs@localhost:54329/pkcs"
    raw_archive_path: Path = Path("data/raw")
    default_top_k: int = Field(default=10, ge=1)
    context_pack_max_evidence: int = Field(default=10, ge=1)
    context_pack_max_evidence_per_source: int = Field(default=3, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()

