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
