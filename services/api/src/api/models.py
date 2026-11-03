"""Wire shapes for the public API (docs/05-api-contract.md)."""

from dataclasses import dataclass
from datetime import datetime

# The contract fixes this order: `states` entries are arrays, not objects.
FIELDS: tuple[str, ...] = (
    "icao24",
    "callsign",
    "lon",
    "lat",
    "alt_m",
    "vel_ms",
    "track_deg",
    "vrate_ms",
    "on_ground",
    "category",
    "squawk",
    "pos_age_s",
)


@dataclass(frozen=True, slots=True)
class StateRow:
    """One aircraft at one snapshot, already normalised to SI units."""

    icao24: str
    callsign: str | None
    lon: float
    lat: float
    alt_m: float | None
    vel_ms: float | None
    track_deg: float | None
    vrate_ms: float | None
    on_ground: bool | None
    category: int | None
    squawk: str | None
    pos_age_s: int | None

    def as_list(self) -> list[object]:
        """Positional form, in `FIELDS` order."""
        return [
            self.icao24,
            self.callsign,
            self.lon,
            self.lat,
            self.alt_m,
            self.vel_ms,
            self.track_deg,
            self.vrate_ms,
            self.on_ground,
            self.category,
            self.squawk,
            self.pos_age_s,
        ]


@dataclass(frozen=True, slots=True)
class Snapshot:
    """All state vectors sharing one `snapshot_time`."""

    snapshot_time: datetime
    states: tuple[StateRow, ...]


@dataclass(frozen=True, slots=True)
class Stats:
    """`GET /stats` numbers, computed in one query."""

    aircraft_now: int
    snapshot_time: datetime | None
    collectors_online: int
    rows_today: int
    dq_status: str | None


@dataclass(frozen=True, slots=True)
class AircraftDetail:
    """`GET /aircraft/{icao24}`. The enrichment fields stay NULL until `ref` and `core` fill."""

    snapshot_time: datetime
    state: StateRow
    registration: str | None
    typecode: str | None
    operator: str | None
    airline: str | None
    flight_id: str | None
    flight_first_seen: datetime | None
    dep_icao: str | None
    dep_source: str | None


@dataclass(frozen=True, slots=True)
class TrackPoint:
    """One deduplicated position in `GET /aircraft/{icao24}/track`."""

    unix_s: int
    lon: float
    lat: float
    alt_m: float | None

    def as_list(self) -> list[object]:
        return [self.unix_s, self.lon, self.lat, self.alt_m]
