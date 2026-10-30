"""Sends spooled batches to ingest-api, oldest first (docs/04-pipelines.md#p1--collector).

Spool files are already gzipped envelopes, so they are posted as they are.
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from enum import Enum, auto
from pathlib import Path

import httpx
import structlog

from collector.spool import Spool

IDLE_POLL_S = 5.0
BACKOFF_MIN_S = 5.0
BACKOFF_MAX_S = 300.0
AUTH_RETRY_S = 300.0
TIMEOUT_S = 60.0

log = structlog.get_logger()

Sleep = Callable[[float], Awaitable[None]]


class Outcome(Enum):
    SENT = auto()
    REJECTED = auto()
    UNAUTHORIZED = auto()
    RETRY = auto()


async def upload_file(client: httpx.AsyncClient, url: str, key: str, path: Path) -> Outcome:
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
    }
    content = await asyncio.to_thread(path.read_bytes)
    try:
        response = await client.post(
            f"{url.rstrip('/')}/batches",
            content=content,
            headers=headers,
            timeout=TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        log.warning("upload_failed", file=path.name, error=type(exc).__name__)
        return Outcome.RETRY
    status = response.status_code
    if 200 <= status < 300:
        return Outcome.SENT
    if status in (413, 422):
        log.error("upload_rejected", file=path.name, http_status=status)
        return Outcome.REJECTED
    if status == 401:
        log.error("upload_unauthorized", file=path.name)
        return Outcome.UNAUTHORIZED
    log.warning("upload_failed", file=path.name, http_status=status)
    return Outcome.RETRY


def _pending(spool: Spool) -> list[Path]:
    return sorted((spool.root / "pending").glob("*.json.gz"))  # UUIDv7 names sort by time


async def run_uploader(
    client: httpx.AsyncClient, url: str, key: str, spool: Spool, sleep: Sleep = asyncio.sleep
) -> None:
    backoff = BACKOFF_MIN_S
    while True:
        try:
            files = _pending(spool)
            if not files:
                await sleep(IDLE_POLL_S)
                continue
            for path in files:
                outcome = await upload_file(client, url, key, path)
                if outcome is Outcome.SENT:
                    os.replace(path, spool.root / "sent" / path.name)
                    backoff = BACKOFF_MIN_S
                elif outcome is Outcome.REJECTED:
                    os.replace(path, spool.root / "rejected" / path.name)
                elif outcome is Outcome.UNAUTHORIZED:
                    await sleep(AUTH_RETRY_S)
                    break
                else:
                    await sleep(backoff)
                    backoff = min(backoff * 2, BACKOFF_MAX_S)
                    break
        except Exception:
            # Uploading must never take down collection; the files stay in pending/.
            log.exception("uploader_crashed")
            await sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_S)
