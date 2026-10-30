"""Database access for ingest-api, as role `ingest_writer`."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool

from airspace_common.live import LIVE_WINDOW_SECONDS
from airspace_common.timefmt import iso_z
from ingest.normalize import Envelope, FlightsQuery, Normalized

# ingest_writer may only INSERT into raw tables, so these temp tables spell out their columns.
_STATES_TEMP = """
CREATE TEMP TABLE batch_rows (
  snapshot_time timestamptz, icao24 text, callsign text, origin_country text,
  time_position timestamptz, last_contact timestamptz, lon double precision, lat double precision,
  baro_altitude_m real, geo_altitude_m real, on_ground boolean, velocity_ms real,
  true_track_deg real, vertical_rate_ms real, squawk text, spi boolean,
  position_source smallint, category smallint, h3_r4 bigint, batch_id uuid
) ON COMMIT DROP
"""
_FLIGHTS_TEMP = """
CREATE TEMP TABLE batch_rows (
  icao24 text, first_seen timestamptz, last_seen timestamptz, callsign text,
  est_dep_icao text, est_arr_icao text, est_dep_horiz_m integer, est_arr_horiz_m integer,
  dep_candidates smallint, arr_candidates smallint, batch_id uuid
) ON COMMIT DROP
"""
_STATES_INSERT = """
INSERT INTO raw.state_vectors (
  snapshot_time, icao24, callsign, origin_country, time_position, last_contact, lon, lat,
  baro_altitude_m, geo_altitude_m, on_ground, velocity_ms, true_track_deg, vertical_rate_ms,
  squawk, spi, position_source, category, h3_r4, batch_id
) SELECT * FROM batch_rows ON CONFLICT DO NOTHING
"""
_FLIGHTS_INSERT = """
INSERT INTO raw.opensky_flights (
  icao24, first_seen, last_seen, callsign, est_dep_icao, est_arr_icao,
  est_dep_horiz_m, est_arr_horiz_m, dep_candidates, arr_candidates, batch_id
) SELECT * FROM batch_rows ON CONFLICT DO NOTHING
"""
_BATCH_INSERT = """
INSERT INTO ops.ingest_batches (
  batch_id, collector_id, query_kind, requested_at, snapshot_time, window_start, window_end,
  http_status, retry_after_s, credits_remaining, n_states, n_inserted, n_rejected
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


@dataclass(frozen=True)
class Collector:
    api_key_hash: str
    disabled: bool


class DuplicateBatch(Exception):
    """Another request stored this `batch_id` first."""


class Store(Protocol):
    def collector(self, collector_id: str) -> Collector | None: ...
    def batch_exists(self, batch_id: UUID) -> bool: ...
    def save(self, envelope: Envelope, normalized: Normalized) -> int: ...
    def ping(self) -> None: ...


def is_live(snapshot_time: datetime, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return snapshot_time >= now - timedelta(seconds=LIVE_WINDOW_SECONDS)


class PgStore:
    def __init__(self, conninfo: str) -> None:
        self.pool = ConnectionPool(conninfo, min_size=1, max_size=4, open=False)

    def collector(self, collector_id: str) -> Collector | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT api_key_hash, disabled_at IS NOT NULL FROM ops.collectors"
                " WHERE collector_id = %s",
                (collector_id,),
            ).fetchone()
        return Collector(row[0], row[1]) if row else None

    def batch_exists(self, batch_id: UUID) -> bool:
        with self.pool.connection() as conn:
            found = conn.execute(
                "SELECT 1 FROM ops.ingest_batches WHERE batch_id = %s", (batch_id,)
            ).fetchone()
        return found is not None

    def save(self, envelope: Envelope, normalized: Normalized) -> int:
        """Stores the rows and the batch row in one transaction. Returns the rows newly stored."""
        query = envelope.query
        is_flights = isinstance(query, FlightsQuery)
        temp, insert = (
            (_FLIGHTS_TEMP, _FLIGHTS_INSERT) if is_flights else (_STATES_TEMP, _STATES_INSERT)
        )
        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                n_inserted = 0
                if normalized.rows:
                    cur.execute(temp)
                    with cur.copy("COPY batch_rows FROM STDIN") as copy:
                        for row in normalized.rows:
                            copy.write_row(row)
                    cur.execute(insert)
                    n_inserted = cur.rowcount
                cur.execute(
                    _BATCH_INSERT,
                    (
                        envelope.batch_id,
                        envelope.collector_id,
                        query.kind,
                        envelope.requested_at,
                        normalized.snapshot_time,
                        query.begin if isinstance(query, FlightsQuery) else None,
                        query.end if isinstance(query, FlightsQuery) else None,
                        envelope.http_status,
                        envelope.retry_after_s,
                        envelope.credits_remaining,
                        normalized.n_states,
                        n_inserted,
                        normalized.n_rejected,
                    ),
                )
                if normalized.snapshot_time is not None and is_live(normalized.snapshot_time):
                    cur.execute(
                        "SELECT pg_notify('new_snapshot', %s)", (iso_z(normalized.snapshot_time),)
                    )
        except psycopg.errors.UniqueViolation as exc:
            raise DuplicateBatch from exc
        return n_inserted

    def ping(self) -> None:
        with self.pool.connection() as conn:
            conn.execute("SELECT 1")
