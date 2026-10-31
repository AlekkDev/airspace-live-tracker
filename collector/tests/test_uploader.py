import asyncio
import gzip
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from collector.spool import Spool
from collector.uploader import AUTH_RETRY_S, BACKOFF_MAX_S, BACKOFF_MIN_S, run_uploader


class Stop(BaseException):
    pass


def spool_with(tmp_path: Path, *names: str) -> Spool:
    spool = Spool(tmp_path)
    for name in names:
        (tmp_path / "pending" / f"{name}.json.gz").write_bytes(gzip.compress(name.encode()))
    return spool


def listing(spool: Spool, folder: str) -> list[str]:
    return sorted(p.name.removesuffix(".json.gz") for p in (spool.root / folder).glob("*"))


def drive(
    spool: Spool, statuses: Callable[[httpx.Request], httpx.Response], max_sleeps: int = 1
) -> tuple[list[httpx.Request], list[float]]:
    """Runs the uploader until it has slept `max_sleeps` times."""
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return statuses(request)

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= max_sleeps:
            raise Stop

    async def main() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await run_uploader(client, "http://vm:8000/ingest/v1/", "the-key", spool, sleep)

    with pytest.raises(Stop):
        asyncio.run(main())
    return requests, sleeps


def test_sends_oldest_first_and_moves_to_sent(tmp_path: Path) -> None:
    spool = spool_with(tmp_path, "02", "01", "03")
    requests, _ = drive(spool, lambda r: httpx.Response(202))
    assert [gzip.decompress(r.content) for r in requests] == [b"01", b"02", b"03"]
    assert listing(spool, "sent") == ["01", "02", "03"]
    assert listing(spool, "pending") == []


def test_request_matches_the_contract(tmp_path: Path) -> None:
    requests, _ = drive(spool_with(tmp_path, "01"), lambda r: httpx.Response(202))
    request = requests[0]
    assert str(request.url) == "http://vm:8000/ingest/v1/batches"
    assert request.headers["authorization"] == "Bearer the-key"
    assert request.headers["content-encoding"] == "gzip"
    assert request.headers["content-type"] == "application/json"


def test_duplicate_counts_as_sent(tmp_path: Path) -> None:
    spool = spool_with(tmp_path, "01")
    drive(spool, lambda r: httpx.Response(200))
    assert listing(spool, "sent") == ["01"]


@pytest.mark.parametrize("status", [413, 422])
def test_rejected_files_move_aside_and_the_next_one_is_sent(tmp_path: Path, status: int) -> None:
    spool = spool_with(tmp_path, "01", "02")
    answers = iter([httpx.Response(status), httpx.Response(202)])
    drive(spool, lambda r: next(answers))
    assert listing(spool, "rejected") == ["01"]
    assert listing(spool, "sent") == ["02"]


def test_401_keeps_files_and_waits_five_minutes(tmp_path: Path) -> None:
    spool = spool_with(tmp_path, "01", "02")
    requests, sleeps = drive(spool, lambda r: httpx.Response(401))
    assert len(requests) == 1
    assert sleeps == [AUTH_RETRY_S]
    assert listing(spool, "pending") == ["01", "02"]


def test_5xx_backs_off_exponentially_up_to_the_maximum(tmp_path: Path) -> None:
    spool = spool_with(tmp_path, "01")
    _, sleeps = drive(spool, lambda r: httpx.Response(503), max_sleeps=9)
    assert sleeps[:3] == [BACKOFF_MIN_S, BACKOFF_MIN_S * 2, BACKOFF_MIN_S * 4]
    assert sleeps[-1] == BACKOFF_MAX_S
    assert listing(spool, "pending") == ["01"]


def test_unreachable_server_keeps_files(tmp_path: Path) -> None:
    spool = spool_with(tmp_path, "01")

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    drive(spool, refuse)
    assert listing(spool, "pending") == ["01"]


def test_backoff_resets_after_a_success(tmp_path: Path) -> None:
    spool = spool_with(tmp_path, "01", "02")
    answers = iter(
        [httpx.Response(503), httpx.Response(202), httpx.Response(503), httpx.Response(202)]
    )
    _, sleeps = drive(spool, lambda r: next(answers), max_sleeps=2)
    assert sleeps == [BACKOFF_MIN_S, BACKOFF_MIN_S]


def test_unexpected_errors_do_not_escape(tmp_path: Path) -> None:
    spool = spool_with(tmp_path, "01")

    def explode(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("bug")

    _, sleeps = drive(spool, explode)
    assert sleeps == [BACKOFF_MIN_S]
    assert listing(spool, "pending") == ["01"]


def test_ignores_files_still_being_written(tmp_path: Path) -> None:
    spool = spool_with(tmp_path, "01")
    (tmp_path / "pending" / "02.json.gz.tmp").write_bytes(b"partial")
    requests, _ = drive(spool, lambda r: httpx.Response(202))
    assert len(requests) == 1
