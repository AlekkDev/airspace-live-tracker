from datetime import UTC, datetime

import pytest

from airspace_common.timefmt import iso_z


def test_iso_z_uses_milliseconds_and_z_suffix() -> None:
    ts = datetime(2026, 11, 3, 14, 31, 30, 120_456, tzinfo=UTC)
    assert iso_z(ts) == "2026-11-03T14:31:30.120Z"


def test_iso_z_seconds_precision() -> None:
    ts = datetime(2026, 11, 2, tzinfo=UTC)
    assert iso_z(ts, timespec="seconds") == "2026-11-02T00:00:00Z"


def test_iso_z_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError):
        iso_z(datetime(2026, 11, 3))
