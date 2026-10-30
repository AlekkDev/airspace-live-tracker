"""Daily flight-list task: yesterday's `/flights/all` in 12 two-hour windows
(docs/04-pipelines.md#p1--collector). Progress per day is kept in `spool/state/` so a restart
neither repeats nor skips windows."""

import asyncio
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import structlog

from airspace_common.timefmt import iso_z
from collector.spool import Spool, make_envelope, write_atomic
from collector.states import Fetcher

START = timedelta(hours=6)
GIVE_UP = timedelta(hours=18)
RETRY_AFTER = timedelta(hours=1)
WINDOW = timedelta(hours=2)
MIN_WINDOW = timedelta(minutes=30)
POLL_INTERVAL_S = 60
STATE_KEEP_DAYS = 7

log = structlog.get_logger()

Window = dict[str, str]  # begin, end, status (pending | done | split | failed), next_attempt


def day_windows(day: date) -> list[tuple[datetime, datetime]]:
    start = datetime.combine(day, time(), tzinfo=UTC)
    return [(start + i * WINDOW, start + (i + 1) * WINDOW) for i in range(12)]


async def flight_list_pass(
    now: datetime, opensky: Fetcher, spool: Spool, collector_id: str
) -> None:
    """Fetch every window of yesterday that is due at `now`."""
    today = datetime.combine(now.date(), time(), tzinfo=UTC)
    if now < today + START:
        return
    day = now.date() - timedelta(days=1)
    path = spool.state_dir / f"flights_{day.isoformat()}.json"
    windows = _load(path) or [_pending(b, e, now) for b, e in day_windows(day)]
    give_up = now >= today + GIVE_UP

    i = 0
    while i < len(windows):  # grows when a window is split
        w = windows[i]
        i += 1
        if w["status"] != "pending" or datetime.fromisoformat(w["next_attempt"]) > now:
            continue
        begin, end = datetime.fromisoformat(w["begin"]), datetime.fromisoformat(w["end"])
        result = await opensky.get(
            "/flights/all", {"begin": int(begin.timestamp()), "end": int(end.timestamp())}
        )
        status = result.http_status
        if status == 200 and result.body:
            _spool(spool, collector_id, begin, end, result)
            w["status"] = "done"
        elif status == 400 and end - begin > MIN_WINDOW:
            mid = begin + (end - begin) / 2
            w["status"] = "split"
            windows += [_pending(begin, mid, now), _pending(mid, end, now)]
        elif status == 400 or give_up:
            _spool(spool, collector_id, begin, end, result)
            w["status"] = "failed"
        else:  # not ready (404 or empty), rate-limited or unreachable
            w["next_attempt"] = iso_z(now + RETRY_AFTER, "seconds")
        log.info(
            "flight_list_window",
            begin=w["begin"],
            end=w["end"],
            http_status=status,
            outcome=w["status"],
        )
        _save(path, windows)

    _prune(spool.state_dir, day - timedelta(days=STATE_KEEP_DAYS))


async def run_flight_lists(opensky: Fetcher, spool: Spool, collector_id: str) -> None:
    while True:
        try:
            await flight_list_pass(datetime.now(UTC), opensky, spool, collector_id)
        except Exception:
            log.exception("flight_lists_pass_crashed")
        await asyncio.sleep(POLL_INTERVAL_S)


def _spool(spool: Spool, collector_id: str, begin: datetime, end: datetime, result: Any) -> None:
    spool.write(
        make_envelope(
            collector_id=collector_id,
            query={
                "kind": "flights_all",
                "begin": iso_z(begin, "seconds"),
                "end": iso_z(end, "seconds"),
            },
            requested_at=result.requested_at,
            http_status=result.http_status,
            retry_after_s=result.retry_after_s,
            credits_remaining=result.credits_remaining,
            response=result.body,
        )
    )


def _pending(begin: datetime, end: datetime, now: datetime) -> Window:
    return {
        "begin": iso_z(begin, "seconds"),
        "end": iso_z(end, "seconds"),
        "status": "pending",
        "next_attempt": iso_z(now, "seconds"),
    }


def _load(path: Path) -> list[Window] | None:
    if not path.exists():
        return None
    windows: list[Window] = json.loads(path.read_text(encoding="utf-8"))["windows"]
    return windows


def _save(path: Path, windows: list[Window]) -> None:
    write_atomic(path, json.dumps({"windows": windows}, indent=1).encode())


def _prune(state_dir: Path, older_than: date) -> None:
    for path in state_dir.glob("flights_*.json"):
        if date.fromisoformat(path.stem.removeprefix("flights_")) < older_than:
            path.unlink()
