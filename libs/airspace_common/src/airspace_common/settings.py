"""Configuration for every service, read from environment variables and `.env` in the working
directory. Every variable is documented in `.env.example`."""

from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollectorSettings(BaseSettings):
    """P1 collector (docs/04-pipelines.md#p1--collector)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    collector_id: str
    opensky_client_id: str
    opensky_client_secret: SecretStr
    ingest_url: str | None = None
    ingest_api_key: SecretStr | None = None
    cadence_seconds: int = 90
    offset_seconds: int
    spool_dir: Path = Path("spool")
    upload_enabled: bool = True
    flight_lists_enabled: bool = True

    @field_validator("offset_seconds")
    @classmethod
    def _offset_on_the_shared_grid(cls, value: int) -> int:
        if value not in (0, 45):
            raise ValueError("OFFSET_SECONDS must be 0 (pc-daniel) or 45 (pc-alek)")
        return value
