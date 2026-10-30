"""Timestamp formatting for the API contract: ISO-8601 UTC with a `Z` suffix."""

from datetime import UTC, datetime
from typing import Literal


def iso_z(ts: datetime, timespec: Literal["seconds", "milliseconds"] = "milliseconds") -> str:
    if ts.tzinfo is None:
        raise ValueError("naive datetime; use timezone-aware UTC datetimes")
    return ts.astimezone(UTC).isoformat(timespec=timespec).replace("+00:00", "Z")
