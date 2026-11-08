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


class IngestSettings(BaseSettings):
    """P2 ingest-api (docs/04-pipelines.md#p2--ingest), connecting as `ingest_writer`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: SecretStr


class ApiSettings(BaseSettings):
    """public-api (docs/05-api-contract.md), connecting as `app_reader`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: SecretStr


class AdminSettings(BaseSettings):
    """Ingest admin CLI, connecting as `airspace_owner`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    admin_database_url: SecretStr


class BackupSettings(BaseSettings):
    """The `backup` job (docs/04-pipelines.md#backup), connecting as the read-only `backup` role.
    The rclone remote itself is configured by `RCLONE_CONFIG_<REMOTE>_*` variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    backup_password: SecretStr
    backup_db_host: str = "db"
    backup_remote: str = "r2"
    backup_bucket: str = "airspace-backup"
    archive_bucket: str = "airspace-archive"
    backup_keep_days: int = 14
    # D7: backups plus archives stay under this, below R2's 10 GB free tier.
    r2_cap_bytes: int = 8_000_000_000
