"""public-api read endpoints (`docs/05-api-contract.md`)."""

import asyncio
import contextlib
import json
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from airspace_common.log import configure_logging
from airspace_common.settings import ApiSettings
from airspace_common.timefmt import iso_z
from api.models import FIELDS, AircraftDetail, EventRow, Snapshot, StateRow
from api.notifier import EVENT_CHANNEL, SNAPSHOT_CHANNEL, Notifier, Notify, PgNotifier
from api.store import Bbox, PgStore, Store

CADENCE_SECONDS = 90
DEGRADED_AFTER_SECONDS = 300
MAX_TRACK_MINUTES = 240
DEFAULT_EVENT_LIMIT = 50
MAX_EVENT_LIMIT = 100
SSE_KEEPALIVE_SECONDS = 20
API_PREFIX = "/api/v1"

log = structlog.get_logger()


class BadRequest(Exception):
    """A client-side parameter error, answered with 422 and an error envelope."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def parse_bbox(raw: str) -> Bbox:
    parts = raw.split(",")
    if len(parts) != 4:
        raise BadRequest("invalid_bbox", "bbox must be minLon,minLat,maxLon,maxLat")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(part) for part in parts)
    except ValueError as exc:
        raise BadRequest("invalid_bbox", "bbox values must be numbers") from exc
    if not (-180 <= min_lon <= max_lon <= 180) or not (-90 <= min_lat <= max_lat <= 90):
        raise BadRequest("invalid_bbox", "bbox is outside the world, or min is greater than max")
    return min_lon, min_lat, max_lon, max_lat


def parse_snapshot_time(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BadRequest("invalid_timestamp", "t must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise BadRequest("invalid_timestamp", "t must carry a timezone, for example the Z suffix")
    return parsed.astimezone(UTC)


def parse_minutes(raw: str | None) -> int:
    if raw is None:
        return 60
    try:
        minutes = int(raw)
    except ValueError as exc:
        raise BadRequest("invalid_minutes", "minutes must be a whole number") from exc
    if not 1 <= minutes <= MAX_TRACK_MINUTES:
        raise BadRequest("invalid_minutes", f"minutes must be between 1 and {MAX_TRACK_MINUTES}")
    return minutes


def parse_limit(raw: str | None) -> int:
    if raw is None:
        return DEFAULT_EVENT_LIMIT
    try:
        limit = int(raw)
    except ValueError as exc:
        raise BadRequest("invalid_limit", "limit must be a whole number") from exc
    if not 1 <= limit <= MAX_EVENT_LIMIT:
        raise BadRequest("invalid_limit", f"limit must be between 1 and {MAX_EVENT_LIMIT}")
    return limit


def parse_cursor(before_ts: str | None, before_id: str | None) -> tuple[datetime, int] | None:
    """The `(ts, event_id)` pair of the previous page, or None for the first page."""
    if before_ts is None and before_id is None:
        return None
    if before_ts is None or before_id is None:
        raise BadRequest("invalid_cursor", "before_ts and before_id must be passed together")
    try:
        event_id = int(before_id)
    except ValueError as exc:
        raise BadRequest("invalid_cursor", "before_id must be a whole number") from exc
    try:
        return parse_snapshot_time(before_ts), event_id
    except BadRequest as exc:
        raise BadRequest("invalid_cursor", str(exc)) from exc


def _last_state(state: StateRow, at: datetime) -> dict[str, Any]:
    return {
        "time": iso_z(at, "seconds"),
        "lon": state.lon,
        "lat": state.lat,
        "alt_m": state.alt_m,
        "vel_ms": state.vel_ms,
        "track_deg": state.track_deg,
        "vrate_ms": state.vrate_ms,
        "pos_age_s": state.pos_age_s,
    }


def snapshot_payload(snapshot: Snapshot) -> dict[str, Any]:
    return {
        "snapshot_time": iso_z(snapshot.snapshot_time, "seconds"),
        "next_expected_at": iso_z(
            snapshot.snapshot_time + timedelta(seconds=CADENCE_SECONDS), "seconds"
        ),
        "fields": list(FIELDS),
        "states": [state.as_list() for state in snapshot.states],
    }


def event_payload(event: EventRow) -> dict[str, Any]:
    """The shape of one event in `/events` and in the SSE `event` frame."""
    return {
        "event_id": event.event_id,
        "ts": iso_z(event.ts, "seconds"),
        "kind": event.kind,
        "severity": event.severity,
        "title": event.title,
        "icao24": event.icao24,
        "airport_icao": event.airport_icao,
        "lon": event.lon,
        "lat": event.lat,
    }


def _sse(event: str, data: dict[str, Any]) -> str:
    """One SSE frame: an event name, one data line, and a blank line to terminate it."""
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def sse_frames(store: Store, notifier: Notifier) -> AsyncIterator[str]:
    """Turn database notifications into SSE frames, with a keep-alive every 20 s.

    The listener runs in a worker thread and posts each notification into an asyncio queue,
    so the frame loop can wait on that queue with a timeout: the timeout is what produces the
    keep-alive. Waiting directly on a blocking source would freeze the event loop instead.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Notify | None] = asyncio.Queue(maxsize=256)
    stop = threading.Event()

    def post(item: Notify | None) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(item)

    def pump() -> None:
        try:
            for note in notifier.listen(stop):
                loop.call_soon_threadsafe(post, note)
        except Exception:
            log.exception("stream_source_failed")
        finally:
            # `None` tells the frame loop that the source has ended.
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(post, None)

    thread = threading.Thread(target=pump, name="sse-listener", daemon=True)
    thread.start()
    try:
        while True:
            try:
                note = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if note is None:
                return
            frame = await _frame_for(store, note)
            if frame is not None:
                yield frame
    finally:
        stop.set()


async def _frame_for(store: Store, note: Notify) -> str | None:
    """Map one notification to one frame; unknown channels and dangling ids are dropped."""
    if note.channel == SNAPSHOT_CHANNEL:
        payload = note.payload.strip()
        return None if not payload else _sse("snapshot_ready", {"snapshot_time": payload})
    if note.channel == EVENT_CHANNEL:
        try:
            event_id = int(note.payload)
        except ValueError:
            log.warning("stream_bad_event_payload", payload=note.payload)
            return None
        row = await run_in_threadpool(store.event, event_id)
        return None if row is None else _sse("event", event_payload(row))
    return None


def aircraft_payload(detail: AircraftDetail) -> dict[str, Any]:
    flight = None
    if detail.flight_id is not None:
        flight = {
            "flight_id": detail.flight_id,
            "first_seen": None
            if detail.flight_first_seen is None
            else iso_z(detail.flight_first_seen, "seconds"),
            "dep_icao": detail.dep_icao,
            "dep_source": detail.dep_source,
        }
    return {
        "icao24": detail.state.icao24,
        "callsign": detail.state.callsign,
        "registration": detail.registration,
        "typecode": detail.typecode,
        "operator": detail.operator,
        "airline": detail.airline,
        "last_state": _last_state(detail.state, detail.snapshot_time),
        "flight": flight,
        "destination": None,
        "eta": None,
    }


def build_app(store: Store, notifier: Notifier) -> FastAPI:
    app = FastAPI(
        title="airspace public-api",
        docs_url=None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    router = APIRouter(prefix=API_PREFIX)

    @router.get("/live/snapshot")
    async def live_snapshot(bbox: str | None = None, t: str | None = None) -> JSONResponse:
        try:
            box = parse_bbox(bbox) if bbox else None
            at = parse_snapshot_time(t) if t else None
        except BadRequest as exc:
            return _error(422, exc.code, exc.message)
        try:
            snapshot = await run_in_threadpool(store.snapshot, at, box)
        except Exception:
            log.exception("snapshot_query_failed")
            return _error(503, "database_unavailable", "the database is not reachable")
        if snapshot is None:
            if at is not None:
                return _error(404, "snapshot_not_found", "no state vectors at that snapshot_time")
            return _error(503, "no_live_data", "no snapshot in the last 10 minutes")
        headers = (
            {"Cache-Control": "public, max-age=86400, immutable"}
            if at is not None
            else {"Cache-Control": "no-store"}
        )
        return JSONResponse(snapshot_payload(snapshot), headers=headers)

    @router.get("/aircraft/{icao24}")
    async def aircraft(icao24: str) -> JSONResponse:
        try:
            detail = await run_in_threadpool(store.aircraft, icao24.strip().lower())
        except Exception:
            log.exception("aircraft_query_failed", icao24=icao24)
            return _error(503, "database_unavailable", "the database is not reachable")
        if detail is None:
            return _error(
                404, "aircraft_not_found", "no state vectors for that icao24 in the last 30 minutes"
            )
        return JSONResponse(aircraft_payload(detail))

    @router.get("/aircraft/{icao24}/track")
    async def aircraft_track(icao24: str, minutes: str | None = None) -> JSONResponse:
        try:
            window = parse_minutes(minutes)
        except BadRequest as exc:
            return _error(422, exc.code, exc.message)
        key = icao24.strip().lower()
        try:
            points = await run_in_threadpool(store.track, key, window)
        except Exception:
            log.exception("track_query_failed", icao24=key)
            return _error(503, "database_unavailable", "the database is not reachable")
        return JSONResponse(
            {"icao24": key, "points": [point.as_list() for point in points]},
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/live/stream")
    async def live_stream() -> StreamingResponse:
        # `X-Accel-Buffering: no` stops nginx-style proxies buffering the stream into silence.
        return StreamingResponse(
            sse_frames(store, notifier),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/events")
    async def events(
        limit: str | None = None, before_ts: str | None = None, before_id: str | None = None
    ) -> JSONResponse:
        try:
            size = parse_limit(limit)
            cursor = parse_cursor(before_ts, before_id)
        except BadRequest as exc:
            return _error(422, exc.code, exc.message)
        try:
            rows = await run_in_threadpool(store.events, size, cursor)
        except Exception:
            log.exception("events_query_failed")
            return _error(503, "database_unavailable", "the database is not reachable")
        next_cursor = None
        if len(rows) == size:
            last = rows[-1]
            next_cursor = {"before_ts": iso_z(last.ts, "seconds"), "before_id": last.event_id}
        return JSONResponse(
            {"events": [event_payload(row) for row in rows], "next_cursor": next_cursor},
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/stats")
    async def stats() -> JSONResponse:
        try:
            numbers = await run_in_threadpool(store.stats)
        except Exception:
            log.exception("stats_query_failed")
            return _error(503, "database_unavailable", "the database is not reachable")
        return JSONResponse(
            {
                "aircraft_now": numbers.aircraft_now,
                "snapshot_time": None
                if numbers.snapshot_time is None
                else iso_z(numbers.snapshot_time, "seconds"),
                "collectors_online": numbers.collectors_online,
                "rows_today": numbers.rows_today,
                "dq_status": numbers.dq_status,
            },
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/health")
    async def health() -> JSONResponse:
        try:
            last = await run_in_threadpool(store.last_snapshot_time)
        except Exception:
            log.exception("health_query_failed")
            return JSONResponse(
                {"status": "degraded", "db": "error", "last_snapshot_age_s": None}, status_code=503
            )
        age = None if last is None else int((datetime.now(UTC) - last).total_seconds())
        status = "ok" if age is not None and age <= DEGRADED_AFTER_SECONDS else "degraded"
        return JSONResponse({"status": status, "db": "ok", "last_snapshot_age_s": age})

    app.include_router(router)
    return app


def create_app() -> FastAPI:
    """Entry point for uvicorn."""
    settings = ApiSettings()
    configure_logging("api")
    dsn = settings.database_url.get_secret_value()
    store = PgStore(dsn)
    notifier = PgNotifier(dsn)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        store.open()
        try:
            yield
        finally:
            store.close()

    app = build_app(store, notifier)
    app.router.lifespan_context = lifespan
    return app
