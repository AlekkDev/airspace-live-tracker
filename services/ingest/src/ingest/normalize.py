"""Envelope validation and row normalisation (docs/04-pipelines.md#p2--ingest)."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import h3
from pydantic import AwareDatetime, BaseModel, Field

H3_RESOLUTION = 4
ICAO24 = re.compile(r"[0-9a-f]{6}")


class StatesQuery(BaseModel):
    kind: Literal["states_global"]


class FlightsQuery(BaseModel):
    kind: Literal["flights_all"]
    begin: AwareDatetime
    end: AwareDatetime


class Envelope(BaseModel):
    batch_id: UUID
    collector_id: str
    query: Annotated[StatesQuery | FlightsQuery, Field(discriminator="kind")]
    requested_at: AwareDatetime
    http_status: int = Field(ge=0, le=999)
    retry_after_s: int | None = None
    credits_remaining: int | None = None
    response: Any = None


@dataclass(frozen=True)
class Normalized:
    rows: list[tuple[Any, ...]]
    n_states: int
    n_rejected: int
    snapshot_time: datetime | None = None


class InvalidBatch(ValueError):
    """The envelope itself is unusable (HTTP 422), as opposed to single bad rows."""


class _BadRow(ValueError):
    pass


def normalize(envelope: Envelope) -> Normalized:
    """Failed OpenSky requests have no rows. They are still stored, so gaps are explained."""
    if envelope.http_status != 200:
        return Normalized([], 0, 0)
    if envelope.query.kind == "states_global":
        return _normalize_states(envelope.response, envelope.batch_id)
    return _normalize_flights(envelope.response, envelope.batch_id)


def _normalize_states(response: Any, batch_id: UUID) -> Normalized:
    if not isinstance(response, dict) or not _is_int(response.get("time")):
        raise InvalidBatch("states_global response needs an integer `time`")
    states = response.get("states")
    if states is None:
        states = []
    if not isinstance(states, list):
        raise InvalidBatch("`states` must be a list")
    snapshot_time = _ts(response["time"])
    assert snapshot_time is not None
    rows = []
    rejected = 0
    for raw in states:
        try:
            rows.append(_state_row(raw, snapshot_time, batch_id))
        except _BadRow:
            rejected += 1
    return Normalized(rows, len(states), rejected, snapshot_time)


def _state_row(raw: Any, snapshot_time: datetime, batch_id: UUID) -> tuple[Any, ...]:
    # OpenSky's order; index 12 is `sensors` (always null without a serial filter).
    if not isinstance(raw, list) or len(raw) < 17:
        raise _BadRow
    lon, lat = _float(raw[5]), _float(raw[6])
    if lat is not None and not -90 <= lat <= 90:
        raise _BadRow
    if lon is not None and not -180 <= lon <= 180:
        raise _BadRow
    h3_r4 = None
    if lat is not None and lon is not None:
        h3_r4 = h3.str_to_int(h3.latlng_to_cell(lat, lon, H3_RESOLUTION))
    return (
        snapshot_time,
        _icao24(raw[0]),
        _text(raw[1]),
        _text(raw[2]),
        _ts(raw[3]),
        _ts(raw[4]),
        lon,
        lat,
        _float(raw[7]),
        _float(raw[13]),
        _bool(raw[8]),
        _float(raw[9]),
        _float(raw[10]),
        _float(raw[11]),
        _text(raw[14]),
        _bool(raw[15]),
        _int(raw[16]),
        _int(raw[17]) if len(raw) > 17 else None,
        h3_r4,
        batch_id,
    )


def _normalize_flights(response: Any, batch_id: UUID) -> Normalized:
    if not isinstance(response, list):
        raise InvalidBatch("flights_all response must be a list")
    rows = []
    rejected = 0
    for raw in response:
        try:
            rows.append(_flight_row(raw, batch_id))
        except _BadRow:
            rejected += 1
    return Normalized(rows, len(response), rejected)


def _flight_row(raw: Any, batch_id: UUID) -> tuple[Any, ...]:
    if not isinstance(raw, dict):
        raise _BadRow
    first_seen, last_seen = _ts(raw.get("firstSeen")), _ts(raw.get("lastSeen"))
    if first_seen is None or last_seen is None:
        raise _BadRow
    return (
        _icao24(raw.get("icao24")),
        first_seen,
        last_seen,
        _text(raw.get("callsign")),
        _text(raw.get("estDepartureAirport")),
        _text(raw.get("estArrivalAirport")),
        _int(raw.get("estDepartureAirportHorizDistance")),
        _int(raw.get("estArrivalAirportHorizDistance")),
        _int(raw.get("departureAirportCandidatesCount")),
        _int(raw.get("arrivalAirportCandidatesCount")),
        batch_id,
    )


def _icao24(value: Any) -> str:
    if not isinstance(value, str):
        raise _BadRow
    icao24 = value.strip().lower()
    if not ICAO24.fullmatch(icao24):
        raise _BadRow
    return icao24


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or "\x00" in value:  # Postgres text cannot hold NUL
        raise _BadRow
    return value.strip() or None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _ts(value: Any) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(_require_int(value), UTC)


def _int(value: Any) -> int | None:
    return None if value is None else _require_int(value)


def _require_int(value: Any) -> int:
    if not _is_int(value):
        raise _BadRow
    return int(value)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _BadRow
    return float(value)


def _bool(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise _BadRow
