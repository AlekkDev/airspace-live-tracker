import asyncio
from pathlib import Path

from fakes import FakeOpenSky, result, scripted

from collector.spool import Spool
from collector.states import collect_slot

SNAPSHOT = {"time": 1793716290, "states": [["4b1805", "SWR283  "]]}


def run_slot(fake: FakeOpenSky, spool_dir: Path) -> list[float]:
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    asyncio.run(collect_slot(fake, Spool(spool_dir), "pc-daniel", sleep=sleep))
    return sleeps


def test_success_is_spooled_as_states_global(tmp_path: Path, read_pending) -> None:
    fake = FakeOpenSky(scripted(result(200, SNAPSHOT)))
    assert run_slot(fake, tmp_path) == []
    [env] = read_pending(tmp_path)
    assert env["query"] == {"kind": "states_global", "extended": True}
    assert env["collector_id"] == "pc-daniel"
    assert (env["http_status"], env["response"]) == (200, SNAPSHOT)
    assert fake.calls == [("/states/all", {"extended": 1})]


def test_5xx_is_retried_once_after_10_seconds(tmp_path: Path, read_pending) -> None:
    fake = FakeOpenSky(scripted(result(503), result(200, SNAPSHOT)))
    assert run_slot(fake, tmp_path) == [10]
    [env] = read_pending(tmp_path)
    assert env["http_status"] == 200


def test_second_failure_spools_one_failed_envelope(tmp_path: Path, read_pending) -> None:
    fake = FakeOpenSky(scripted(result(0), result(503)))
    run_slot(fake, tmp_path)
    [env] = read_pending(tmp_path)
    assert (env["http_status"], env["response"]) == (503, None)


def test_429_is_spooled_without_retry(tmp_path: Path, read_pending) -> None:
    fake = FakeOpenSky(scripted(result(429, retry_after=600)))
    assert run_slot(fake, tmp_path) == []
    [env] = read_pending(tmp_path)
    assert (env["http_status"], env["retry_after_s"]) == (429, 600)
