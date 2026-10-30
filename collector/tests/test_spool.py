import gzip
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from collector.spool import Spool, make_envelope

REQUESTED_AT = datetime(2026, 11, 3, 14, 31, 30, 120_000, tzinfo=UTC)


def envelope() -> dict[str, object]:
    return make_envelope(
        collector_id="pc-daniel",
        query={"kind": "states_global", "extended": True},
        requested_at=REQUESTED_AT,
        http_status=200,
        retry_after_s=None,
        credits_remaining=3120,
        response={"time": 1793716290, "states": []},
    )


def test_envelope_matches_the_api_contract() -> None:
    env = envelope()
    assert list(env) == [
        "batch_id",
        "collector_id",
        "query",
        "requested_at",
        "http_status",
        "retry_after_s",
        "credits_remaining",
        "response",
    ]
    assert env["requested_at"] == "2026-11-03T14:31:30.120Z"


def test_batch_id_is_uuid7() -> None:
    assert uuid.UUID(str(envelope()["batch_id"])).version == 7


def test_spool_creates_its_directories(tmp_path: Path) -> None:
    Spool(tmp_path)
    for name in ("pending", "sent", "rejected", "archive", "state"):
        assert (tmp_path / name).is_dir()


def test_write_stores_gzipped_json_named_by_batch_id(tmp_path: Path) -> None:
    env = envelope()
    path = Spool(tmp_path).write(env)
    assert path == tmp_path / "pending" / f"{env['batch_id']}.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as f:
        assert json.load(f) == env
    assert not list((tmp_path / "pending").glob("*.tmp"))
