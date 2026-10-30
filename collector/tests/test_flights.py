import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fakes import FakeOpenSky, result

from collector.flights import day_windows, flight_list_pass
from collector.opensky import FetchResult
from collector.spool import Spool

DAY = date(2026, 11, 2)
FLIGHT = {"icao24": "4b1805", "firstSeen": 1793577600, "callsign": "SWR283  "}
FIRST_BEGIN = int(datetime(2026, 11, 2, 0, tzinfo=UTC).timestamp())


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 3, hour, minute, tzinfo=UTC)


def always(status: int, body: Any = None) -> Any:
    return lambda path, params: result(status, body)


def first_window(status: int, body: Any = None) -> Any:
    """`status` for windows starting at 00:00 on DAY, a good flight list for every other one."""

    def respond(path: str, params: dict[str, Any]) -> FetchResult:
        if params["begin"] == FIRST_BEGIN:
            return result(status, body)
        return result(200, [FLIGHT])

    return respond


def run_pass(now: datetime, fake: FakeOpenSky, spool_dir: Path) -> None:
    asyncio.run(flight_list_pass(now, fake, Spool(spool_dir), "pc-daniel"))


def test_day_is_twelve_two_hour_windows() -> None:
    windows = day_windows(DAY)
    assert len(windows) == 12
    assert windows[0] == (
        datetime(2026, 11, 2, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 2, tzinfo=UTC),
    )
    assert windows[-1][1] == datetime(2026, 11, 3, tzinfo=UTC)


def test_nothing_happens_before_06_utc(tmp_path: Path) -> None:
    fake = FakeOpenSky(always(200, [FLIGHT]))
    run_pass(at(5, 59), fake, tmp_path)
    assert fake.calls == []


def test_yesterday_is_fetched_once_from_06_utc(tmp_path: Path, read_pending) -> None:
    fake = FakeOpenSky(always(200, [FLIGHT]))
    run_pass(at(6), fake, tmp_path)
    run_pass(at(6, 1), fake, tmp_path)
    assert len(fake.calls) == 12
    assert fake.calls[0] == ("/flights/all", {"begin": FIRST_BEGIN, "end": FIRST_BEGIN + 7200})
    envs = read_pending(tmp_path)
    assert len(envs) == 12
    assert envs[0]["query"] == {
        "kind": "flights_all",
        "begin": "2026-11-02T00:00:00Z",
        "end": "2026-11-02T02:00:00Z",
    }
    assert envs[0]["response"] == [FLIGHT]


def test_not_ready_window_is_retried_after_an_hour(tmp_path: Path, read_pending) -> None:
    run_pass(at(6), FakeOpenSky(first_window(404)), tmp_path)
    assert len(read_pending(tmp_path)) == 11

    later = FakeOpenSky(always(200, [FLIGHT]))
    run_pass(at(6, 30), later, tmp_path)
    assert later.calls == []
    run_pass(at(7), later, tmp_path)
    assert len(later.calls) == 1
    assert len(read_pending(tmp_path)) == 12


def test_empty_list_counts_as_not_ready(tmp_path: Path, read_pending) -> None:
    run_pass(at(6), FakeOpenSky(first_window(200, [])), tmp_path)
    assert len(read_pending(tmp_path)) == 11


def test_400_splits_the_window_down_to_30_minutes(tmp_path: Path, read_pending) -> None:
    def respond(path: str, params: dict[str, Any]) -> FetchResult:
        if params["begin"] < FIRST_BEGIN + 7200:
            return result(400)
        return result(200, [FLIGHT])

    fake = FakeOpenSky(respond)
    run_pass(at(6), fake, tmp_path)
    spans = sorted(p["end"] - p["begin"] for _, p in fake.calls if p["begin"] < FIRST_BEGIN + 7200)
    assert spans == [1800] * 4 + [3600] * 2 + [7200]
    failed = [e for e in read_pending(tmp_path) if e["http_status"] == 400]
    assert len(failed) == 4
    assert all(e["response"] is None for e in failed)


def test_after_18_utc_a_failing_window_is_given_up(tmp_path: Path, read_pending) -> None:
    run_pass(at(6), FakeOpenSky(first_window(404)), tmp_path)
    late = FakeOpenSky(always(404))
    run_pass(at(18), late, tmp_path)
    run_pass(at(19), late, tmp_path)
    assert len(late.calls) == 1
    failed = [e for e in read_pending(tmp_path) if e["http_status"] == 404]
    assert len(failed) == 1
    assert failed[0]["response"] is None


def test_first_start_after_18_utc_still_tries_each_window_once(
    tmp_path: Path, read_pending
) -> None:
    fake = FakeOpenSky(always(404))
    run_pass(at(20), fake, tmp_path)
    run_pass(at(21), fake, tmp_path)
    assert len(fake.calls) == 12
    assert len(read_pending(tmp_path)) == 12
