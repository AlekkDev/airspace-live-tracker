"""Read-only database access for public-api, as role `app_reader`."""

from datetime import datetime
from typing import Protocol

from psycopg_pool import ConnectionPool

from airspace_common.live import LIVE_WINDOW_SECONDS
from api.models import Snapshot, StateRow

# minLon, minLat, maxLon, maxLat
Bbox = tuple[float, float, float, float]

_STATES_SQL = """
SELECT icao24, callsign, lon, lat, baro_altitude_m, velocity_ms, true_track_deg,
       vertical_rate_ms, on_ground, category, squawk,
       CASE WHEN time_position IS NULL THEN NULL
            ELSE extract(epoch FROM (%s::timestamptz - time_position))::int END
FROM raw.state_vectors
WHERE snapshot_time = %s AND lat IS NOT NULL AND lon IS NOT NULL
"""

# Appended to `_STATES_SQL`; the bounding box never reaches SQL as text.
_BBOX_SQL = " AND lon >= %s AND lon <= %s AND lat >= %s AND lat <= %s"

_LATEST_LIVE_SQL = """
SELECT max(snapshot_time) FROM raw.state_vectors
WHERE snapshot_time >= now() - make_interval(secs => %s)
"""

_LATEST_ANY_SQL = "SELECT max(snapshot_time) FROM raw.state_vectors"

_SNAPSHOT_EXISTS_SQL = "SELECT 1 FROM raw.state_vectors WHERE snapshot_time = %s LIMIT 1"


class Store(Protocol):
    """The read surface public-api needs; tests replace it with a fake."""

    def snapshot(self, at: datetime | None = None, bbox: Bbox | None = None) -> Snapshot | None:
        """State vectors at `at`, or at the latest live snapshot when `at` is None."""
        ...

    def last_snapshot_time(self) -> datetime | None:
        """The newest `snapshot_time` of any age, for `/health`."""
        ...

    def ping(self) -> None: ...


def _as_float(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


def _as_int(value: object) -> int | None:
    return None if value is None else int(value)  # type: ignore[call-overload]


def _state_row(row: tuple[object, ...]) -> StateRow:
    return StateRow(
        icao24=str(row[0]),
        callsign=None if row[1] is None else str(row[1]),
        lon=float(row[2]),  # type: ignore[arg-type]
        lat=float(row[3]),  # type: ignore[arg-type]
        alt_m=_as_float(row[4]),
        vel_ms=_as_float(row[5]),
        track_deg=_as_float(row[6]),
        vrate_ms=_as_float(row[7]),
        on_ground=None if row[8] is None else bool(row[8]),
        category=_as_int(row[9]),
        squawk=None if row[10] is None else str(row[10]),
        pos_age_s=_as_int(row[11]),
    )


class PgStore:
    """PostgreSQL/TimescaleDB implementation. One short read per request."""

    def __init__(self, dsn: str) -> None:
        self._pool = ConnectionPool(
            dsn, min_size=1, max_size=8, open=False, kwargs={"autocommit": True}
        )

    def open(self) -> None:
        self._pool.open()

    def close(self) -> None:
        self._pool.close()

    def ping(self) -> None:
        with self._pool.connection() as conn:
            conn.execute("SELECT 1")

    def last_snapshot_time(self) -> datetime | None:
        with self._pool.connection() as conn:
            row = conn.execute(_LATEST_ANY_SQL).fetchone()
        return None if row is None else row[0]

    def snapshot(self, at: datetime | None = None, bbox: Bbox | None = None) -> Snapshot | None:
        with self._pool.connection() as conn:
            snapshot_time = at
            if snapshot_time is None:
                latest = conn.execute(_LATEST_LIVE_SQL, (LIVE_WINDOW_SECONDS,)).fetchone()
                snapshot_time = None if latest is None else latest[0]
            if snapshot_time is None:
                return None
            sql = _STATES_SQL
            params: list[object] = [snapshot_time, snapshot_time]
            if bbox is not None:
                min_lon, min_lat, max_lon, max_lat = bbox
                sql += _BBOX_SQL
                params += [min_lon, max_lon, min_lat, max_lat]
            rows = conn.execute(sql, params).fetchall()
            # An explicit `t` must name a real snapshot, even one without positioned rows.
            empty = not rows and at is not None
            if empty and conn.execute(_SNAPSHOT_EXISTS_SQL, (snapshot_time,)).fetchone() is None:
                return None
        return Snapshot(snapshot_time, tuple(_state_row(row) for row in rows))
