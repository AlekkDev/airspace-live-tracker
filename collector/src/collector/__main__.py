"""`uv run -m collector` runs the collector; `uv run -m collector status` summarises the spool."""

import asyncio
import sys

import httpx
import structlog

from airspace_common.log import configure_logging
from airspace_common.settings import CollectorSettings
from collector.flights import run_flight_lists
from collector.lock import AlreadyRunning, single_instance
from collector.opensky import OpenSky, TokenProvider
from collector.spool import Spool
from collector.states import run_states
from collector.status import format_summary, spool_summary

log = structlog.get_logger()


async def run(settings: CollectorSettings) -> None:
    configure_logging("collector", settings.spool_dir / "logs" / "collector.log")
    structlog.contextvars.bind_contextvars(collector_id=settings.collector_id)
    log.info(
        "collector_started",
        cadence_seconds=settings.cadence_seconds,
        offset_seconds=settings.offset_seconds,
        upload_enabled=settings.upload_enabled,
        flight_lists_enabled=settings.flight_lists_enabled,
        spool_dir=str(settings.spool_dir.resolve()),
    )
    if settings.upload_enabled:
        log.warning(
            "uploader_not_built",
            detail="v0 is spool-only; batches stay in spool/pending until the M1 uploader exists",
        )
    spool = Spool(settings.spool_dir)
    async with httpx.AsyncClient() as client:
        tokens = TokenProvider(
            client, settings.opensky_client_id, settings.opensky_client_secret.get_secret_value()
        )
        opensky = OpenSky(client, tokens)
        jobs = [run_states(settings, opensky, spool)]
        if settings.flight_lists_enabled:
            jobs.append(run_flight_lists(opensky, spool, settings.collector_id))
        await asyncio.gather(*jobs)


def main() -> None:
    settings = CollectorSettings()
    if sys.argv[1:] == ["status"]:
        print(f"collector {settings.collector_id}, spool {settings.spool_dir.resolve()}")
        print(format_summary(spool_summary(settings.spool_dir)))
        return
    try:
        with single_instance(settings.spool_dir / "collector.lock"):
            asyncio.run(run(settings))
    except AlreadyRunning as exc:
        sys.exit(f"collector not started: {exc}")


if __name__ == "__main__":
    main()
