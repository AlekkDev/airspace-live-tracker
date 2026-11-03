"""Read-only database access for public-api, as role `app_reader`."""

from datetime import datetime
from typing import Protocol

from psycopg_pool import ConnectionPool

from airspace_common.live import LIVE_WINDOW_SECONDS
from api.models import AircraftDetail, EventRow, Snapshot, StateRow, Stats, TrackPoint

# minLon, minLat, maxLon, maxLat
Bbox = tuple[float, float, float, float]

# Shared by the snapshot and aircraft queries so the two can never drift apart.
# `pos_age_s` is computed from the row's own `snapshot_time`, so no parameter is needed.
_STATE_COLUMNS = """
       icao24, callsign, lon, lat, baro_altitude_m, velocity_ms, true_track_deg,
       vertical_rate_ms, on_ground, category, squawk,
       CASE WHEN time_position IS NULL THEN NULL
            ELSE extract(epoch FROM (snapshot_time - time_position))::int END AS pos_age_s"""

_STATES_SQL = f"""
SELECT {_STATE_COLUMNS}
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

# One round trip. app_reader may not read ops.ingest_batches directly, only the views.
_STATS_SQL = """
WITH latest AS (SELECT max(snapshot_time) AS t FROM raw.state_vectors),
airborne AS (
  SELECT count(*)::int AS n FROM raw.state_vectors v, latest
  WHERE v.snapshot_time = latest.t AND v.lat IS NOT NULL AND v.lon IS NOT NULL
),
online AS (
  SELECT count(DISTINCT collector_id)::int AS n FROM ops.v_ingest_batches
  WHERE http_status = 200 AND received_at > now() - interval '3 minutes'
),
today AS (
  SELECT coalesce(sum(n_inserted), 0)::bigint AS n FROM ops.v_ingest_batches
  WHERE received_at >= (date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')
),
worst_dq AS (
  SELECT status FROM (
    SELECT DISTINCT ON (check_name) check_name, status
    FROM ops.dq_results
    ORDER BY check_name, checked_at DESC
  ) latest_checks
  ORDER BY array_position(ARRAY['fail', 'warn', 'pass']::text[], status) NULLS LAST
  LIMIT 1
)
SELECT (SELECT t FROM latest), (SELECT n FROM airborne), (SELECT n FROM online),
       (SELECT n FROM today), (SELECT status FROM worst_dq)
"""

# LEFT JOINs, so the card works before ref.aircraft and core.flights have rows.
_AIRCRAFT_SQL = f"""
WITH state AS (
  SELECT snapshot_time, {_STATE_COLUMNS}
  FROM raw.state_vectors
  WHERE icao24 = %s AND snapshot_time >= now() - interval '30 minutes'
  ORDER BY snapshot_time DESC
  LIMIT 1
)
SELECT state.*, a.registration, a.typecode, a.operator, al.name,
       f.flight_id::text, f.first_seen, f.dep_icao, f.dep_source
FROM state
LEFT JOIN ref.aircraft a ON a.icao24 = state.icao24
LEFT JOIN ref.airlines al ON al.icao = upper(left(state.callsign, 3))
LEFT JOIN core.flights f ON f.icao24 = state.icao24 AND f.status = 'active'
"""

# DISTINCT ON keeps one point per reported position, taking the freshest snapshot for it.
_TRACK_SQL = """
SELECT * FROM (
  SELECT DISTINCT ON (time_position)
         extract(epoch FROM time_position)::bigint AS unix_s, lon, lat, baro_altitude_m
  FROM raw.state_vectors
  WHERE icao24 = %s
    AND snapshot_time >= now() - make_interval(mins => %s)
    AND time_position IS NOT NULL AND lon IS NOT NULL AND lat IS NOT NULL
  ORDER BY time_position, snapshot_time DESC
) points
ORDER BY unix_s
"""


# Keyset paging: `(ts, event_id)` sorts exactly like the table's index, and the pair keeps
# the cursor stable while new events arrive between page loads.
_EVENTS_SQL = """
SELECT event_id, ts, kind, severity, title, icao24, airport_icao, lon, lat
FROM core.events
{cursor}
ORDER BY ts DESC, event_id DESC
LIMIT %s
"""

_EVENT_SQL = """
SELECT event_id, ts, kind, severity, title, icao24, airport_icao, lon, lat
FROM core.events WHERE event_id = %s
"""


class Store(Protocol):
    """The read surface public-api needs; tests replace it with a fake."""

    def snapshot(self, at: datetime | None = None, bbox: Bbox | None = None) -> Snapshot | None:
        """State vectors at `at`, or at the latest live snapshot when `at` is None."""
        ...

    def last_snapshot_time(self) -> datetime | None:
        """The newest `snapshot_time` of any age, for `/health`."""
        ...

    def stats(self) -> Stats: ...

    def aircraft(self, icao24: str) -> AircraftDetail | None: ...

    def track(self, icao24: str, minutes: int) -> tuple[TrackPoint, ...]: ...

    def events(
        self, limit: int, before: tuple[datetime, int] | None = None
    ) -> tuple[EventRow, ...]:
        """Newest first; `before` is the `(ts, event_id)` cursor of the previous page."""
        ...

    def event(self, event_id: int) -> EventRow | None: ...

    def ping(self) -> None: ...


def _as_float(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


def _as_int(value: object) -> int | None:
    return None if value is None else int(value)  # type: ignore[call-overload]


def _as_str(value: object) -> str | None:
    return None if value is None else str(value)


def _state_row(row: tuple[object, ...]) -> StateRow:
    """Build a `StateRow` from the 12 columns of `_STATE_COLUMNS`."""
    return StateRow(
        icao24=str(row[0]),
        callsign=_as_str(row[1]),
        lon=float(row[2]),  # type: ignore[arg-type]
        lat=float(row[3]),  # type: ignore[arg-type]
        alt_m=_as_float(row[4]),
        vel_ms=_as_float(row[5]),
        track_deg=_as_float(row[6]),
        vrate_ms=_as_float(row[7]),
        on_ground=None if row[8] is None else bool(row[8]),
        category=_as_int(row[9]),
        squawk=_as_str(row[10]),
        pos_age_s=_as_int(row[11]),
    )


def _event_row(row: tuple[object, ...]) -> EventRow:
    return EventRow(
        event_id=int(row[0]),  # type: ignore[call-overload]
        ts=row[1],  # type: ignore[arg-type]
        kind=str(row[2]),
        severity=str(row[3]),
        title=str(row[4]),
        icao24=_as_str(row[5]),
        airport_icao=_as_str(row[6]),
        lon=_as_float(row[7]),
        lat=_as_float(row[8]),
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
            params: list[object] = [snapshot_time]
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

    def stats(self) -> Stats:
        with self._pool.connection() as conn:
            row = conn.execute(_STATS_SQL).fetchone()
        assert row is not None  # a CTE-only query always returns exactly one row
        return Stats(
            aircraft_now=int(row[1]),  # type: ignore[call-overload]
            snapshot_time=row[0],
            collectors_online=int(row[2]),  # type: ignore[call-overload]
            rows_today=int(row[3]),  # type: ignore[call-overload]
            dq_status=_as_str(row[4]),
        )

    def aircraft(self, icao24: str) -> AircraftDetail | None:
        with self._pool.connection() as conn:
            row = conn.execute(_AIRCRAFT_SQL, (icao24,)).fetchone()
        if row is None:
            return None
        return AircraftDetail(
            snapshot_time=row[0],
            state=_state_row(row[1:13]),
            registration=_as_str(row[13]),
            typecode=_as_str(row[14]),
            operator=_as_str(row[15]),
            airline=_as_str(row[16]),
            flight_id=_as_str(row[17]),
            flight_first_seen=row[18],
            dep_icao=_as_str(row[19]),
            dep_source=_as_str(row[20]),
        )

    def track(self, icao24: str, minutes: int) -> tuple[TrackPoint, ...]:
        with self._pool.connection() as conn:
            rows = conn.execute(_TRACK_SQL, (icao24, minutes)).fetchall()
        return tuple(
            TrackPoint(
                unix_s=int(row[0]),  # type: ignore[call-overload]
                lon=float(row[1]),  # type: ignore[arg-type]
                lat=float(row[2]),  # type: ignore[arg-type]
                alt_m=_as_float(row[3]),
            )
            for row in rows
        )

    def events(
        self, limit: int, before: tuple[datetime, int] | None = None
    ) -> tuple[EventRow, ...]:
        cursor = "" if before is None else "WHERE (ts, event_id) < (%s, %s)"
        params: list[object] = [] if before is None else [before[0], before[1]]
        params.append(limit)
        with self._pool.connection() as conn:
            rows = conn.execute(_EVENTS_SQL.format(cursor=cursor), params).fetchall()
        return tuple(_event_row(row) for row in rows)

    def event(self, event_id: int) -> EventRow | None:
        with self._pool.connection() as conn:
            row = conn.execute(_EVENT_SQL, (event_id,)).fetchone()
        return None if row is None else _event_row(row)
