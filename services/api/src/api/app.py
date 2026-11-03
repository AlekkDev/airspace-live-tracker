"""public-api read endpoints (`docs/05-api-contract.md`)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from airspace_common.log import configure_logging
from airspace_common.settings import ApiSettings
from airspace_common.timefmt import iso_z
from api.models import FIELDS, AircraftDetail, Snapshot, StateRow
from api.store import Bbox, PgStore, Store

CADENCE_SECONDS = 90
DEGRADED_AFTER_SECONDS = 300
MAX_TRACK_MINUTES = 240
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


def build_app(store: Store) -> FastAPI:
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
    store = PgStore(settings.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        store.open()
        try:
            yield
        finally:
            store.close()

    app = build_app(store)
    app.router.lifespan_context = lifespan
    return app
