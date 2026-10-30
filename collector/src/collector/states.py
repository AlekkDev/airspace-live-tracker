"""State-vector loop: one global `/states/all` per slot (docs/04-pipelines.md#p1--collector)."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import structlog

from airspace_common.settings import CollectorSettings
from collector.opensky import FetchResult
from collector.slots import next_slot
from collector.spool import Spool, make_envelope

RETRY_DELAY_S = 10
PARAMS = {"extended": 1}

log = structlog.get_logger()

Sleep = Callable[[float], Awaitable[None]]


class Fetcher(Protocol):
    async def get(self, path: str, params: dict[str, Any]) -> FetchResult: ...


async def collect_slot(
    opensky: Fetcher, spool: Spool, collector_id: str, sleep: Sleep = asyncio.sleep
) -> FetchResult:
    """Fetch one snapshot, retrying once after 10 s on 5xx or timeout, and spool the outcome."""
    result = await opensky.get("/states/all", PARAMS)
    if result.http_status == 0 or result.http_status >= 500:
        await sleep(RETRY_DELAY_S)
        result = await opensky.get("/states/all", PARAMS)

    spool.write(
        make_envelope(
            collector_id=collector_id,
            query={"kind": "states_global", "extended": True},
            requested_at=result.requested_at,
            http_status=result.http_status,
            retry_after_s=result.retry_after_s,
            credits_remaining=result.credits_remaining,
            response=result.body,
        )
    )
    n_states = len(result.body.get("states") or []) if isinstance(result.body, dict) else 0
    log.info(
        "states_slot",
        http_status=result.http_status,
        n_states=n_states,
        credits_remaining=result.credits_remaining,
    )
    return result


async def run_states(settings: CollectorSettings, opensky: Fetcher, spool: Spool) -> None:
    cadence, offset = settings.cadence_seconds, settings.offset_seconds
    last_slot = 0.0
    blocked_until = 0.0
    while True:
        slot = max(next_slot(time.time(), cadence, offset), last_slot + cadence)
        await asyncio.sleep(max(0.0, slot - time.time()))
        last_slot = slot
        if time.time() < blocked_until:
            log.info("states_slot_skipped", reason="rate_limited")
            continue
        try:
            result = await collect_slot(opensky, spool, settings.collector_id)
        except Exception:
            log.exception("states_slot_crashed")
            continue
        if result.http_status == 429:
            blocked_until = time.time() + (result.retry_after_s or cadence)
