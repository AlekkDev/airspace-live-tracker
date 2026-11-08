"""The daily `backup` job (docs/04-pipelines.md#backup).

1. `pg_dump -Fc` of `airspace` (without the data of the `raw` hypertables' chunks, which come back
   from the collector's archives), `dagster` and `mlflow`, as the read-only `backup` role.
2. `rclone copy` to `<remote>:airspace-backup/YYYY-MM-DD/`; keep the newest 14 days.
3. Keep R2 under the free tier (D7): when backups and archives together pass the cap, delete the
   oldest files in `airspace-archive`. Backups are never deleted for the cap.

rclone reads its remote from `RCLONE_CONFIG_<REMOTE>_*` environment variables (infra/compose.yml).
"""

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg
from dagster import In, Nothing, OpExecutionContext, ScheduleDefinition, job, op

from airspace_common.settings import BackupSettings

DATABASES = ("airspace", "dagster", "mlflow")

# pg_dump patterns matching every chunk of a `raw` hypertable and the tables holding its
# compressed data. All are named after the hypertable's chunk prefix (`_hyper_1_2_chunk`,
# `_hyper_1_2_chunk_compressed` since TimescaleDB 2.30, which no longer lists those in its
# catalog). Unquoted, so `*` is a wildcard. The restore drill in infra/test-db.sh fails if an
# image upgrade breaks this.
RAW_CHUNK_PATTERNS_SQL = """
SELECT associated_schema_name || '.' || associated_table_prefix || '_*'
FROM _timescaledb_catalog.hypertable
WHERE schema_name = 'raw'
   OR id IN (SELECT compressed_hypertable_id FROM _timescaledb_catalog.hypertable
             WHERE schema_name = 'raw' AND compressed_hypertable_id IS NOT NULL)
ORDER BY 1
"""

RCLONE_DIR_NOT_FOUND = 3


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int
    mod_time: datetime


def exclude_table_data_args(tables: Iterable[str]) -> list[str]:
    return [f"--exclude-table-data={table}" for table in tables]


def backup_days_to_delete(days: Iterable[date], keep: int) -> list[date]:
    """Every backup day except the `keep` newest, oldest first."""
    newest_first = sorted(days, reverse=True)
    return sorted(newest_first[keep:])


def archive_files_to_delete(
    files: Sequence[RemoteFile], other_bytes: int, cap_bytes: int
) -> list[str]:
    """Oldest archive files to delete so archives plus `other_bytes` fit in `cap_bytes`."""
    total = other_bytes + sum(f.size for f in files)
    doomed: list[str] = []
    for f in sorted(files, key=lambda f: (f.mod_time, f.path)):
        if total <= cap_bytes:
            break
        doomed.append(f.path)
        total -= f.size
    return doomed


def _run(
    context: OpExecutionContext, args: Sequence[str], env: Mapping[str, str] | None = None
) -> str:
    context.log.info("running " + " ".join(args))
    result = subprocess.run(args, check=True, capture_output=True, text=True, env=env)
    return result.stdout


def _remote(settings: BackupSettings, bucket: str, path: str = "") -> str:
    return f"{settings.backup_remote}:{bucket}/{path}".rstrip("/")


@op
def dump_databases(context: OpExecutionContext) -> str:
    """Writes `<db>.dump` files to a new temporary directory and returns its path."""
    settings = BackupSettings()
    password = settings.backup_password.get_secret_value()
    with psycopg.connect(
        host=settings.backup_db_host, user="backup", dbname="airspace", password=password
    ) as conn:
        raw_chunks = [row[0] for row in conn.execute(RAW_CHUNK_PATTERNS_SQL)]
    context.log.info(f"excluding table data matching {raw_chunks}")

    out = Path(tempfile.mkdtemp(prefix="backup-"))
    env = {**os.environ, "PGPASSWORD": password}
    for db in DATABASES:
        dump = out / f"{db}.dump"
        args = ["pg_dump", "-Fc", "-h", settings.backup_db_host, "-U", "backup", "-d", db]
        args += ["-f", str(dump)]
        if db == "airspace":
            args += exclude_table_data_args(raw_chunks)
        _run(context, args, env)
        context.log.info(f"{dump.name}: {dump.stat().st_size} bytes")
    return str(out)


@op
def upload_backup(context: OpExecutionContext, dump_dir: str) -> date:
    settings = BackupSettings()
    today = datetime.now(UTC).date()
    try:
        target = _remote(settings, settings.backup_bucket, today.isoformat())
        _run(context, ["rclone", "copy", "--s3-no-check-bucket", dump_dir, target])
    finally:
        shutil.rmtree(dump_dir)
    return today


@op
def prune_backups(context: OpExecutionContext, uploaded: date) -> None:
    settings = BackupSettings()
    bucket = _remote(settings, settings.backup_bucket)
    days = []
    for line in _run(context, ["rclone", "lsf", "--dirs-only", bucket]).splitlines():
        try:
            days.append(date.fromisoformat(line.strip().rstrip("/")))
        except ValueError:
            context.log.warning(f"ignoring unexpected entry {line!r} in the backup bucket")
    if uploaded not in days:
        raise RuntimeError(f"today's backup {uploaded} is missing from the bucket")
    for day in backup_days_to_delete(days, settings.backup_keep_days):
        _run(context, ["rclone", "purge", _remote(settings, settings.backup_bucket, str(day))])
        context.log.info(f"deleted backup {day}")


@op(ins={"after": In(Nothing)})
def enforce_r2_cap(context: OpExecutionContext) -> None:
    settings = BackupSettings()
    backups = json.loads(
        _run(context, ["rclone", "size", "--json", _remote(settings, settings.backup_bucket)])
    )
    archive = _remote(settings, settings.archive_bucket)
    try:
        listing = _run(context, ["rclone", "lsjson", "-R", "--files-only", archive])
    except subprocess.CalledProcessError as exc:
        if exc.returncode != RCLONE_DIR_NOT_FOUND:
            raise
        listing = "[]"  # the collector has not uploaded any archives yet
    files = [
        RemoteFile(f["Path"], int(f["Size"]), datetime.fromisoformat(f["ModTime"]))
        for f in json.loads(listing)
    ]
    backup_bytes = int(backups["bytes"])
    context.log.info(
        f"R2 usage: backups {backup_bytes} B, archives {sum(f.size for f in files)} B, "
        f"cap {settings.r2_cap_bytes} B"
    )
    for path in archive_files_to_delete(files, backup_bytes, settings.r2_cap_bytes):
        _run(context, ["rclone", "deletefile", _remote(settings, settings.archive_bucket, path)])
        context.log.info(f"deleted archive {path} to stay under the cap")


@job(description="Daily database backup to R2: 14 days kept, R2 kept under the free tier (D7).")
def backup() -> None:
    enforce_r2_cap(prune_backups(upload_backup(dump_databases())))


backup_schedule = ScheduleDefinition(
    job=backup, cron_schedule="0 4 * * *", execution_timezone="UTC"
)
