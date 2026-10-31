import gzip
import json
from typing import Any
from uuid import UUID

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from ingest.app import build_app
from ingest.normalize import Envelope, Normalized
from ingest.store import Collector, DuplicateBatch

KEY = "right-key"
HASH = PasswordHasher().hash(KEY)
STATE = ["4b1805", "SWR283", "CH", 1, 2, 16.12, 48.02, 1.0, False, 2.0, 3.0, 0.0, None, 1.0, None]
STATE += [False, 0, 4]
ENVELOPE = {
    "batch_id": "0192f0c4-0000-7000-8000-000000000001",
    "collector_id": "pc-daniel",
    "query": {"kind": "states_global", "extended": True},
    "requested_at": "2026-11-03T14:31:30.120Z",
    "http_status": 200,
    "retry_after_s": None,
    "credits_remaining": 3120,
    "response": {"time": 1793716290, "states": [STATE]},
}


class FakeStore:
    def __init__(self) -> None:
        self.collectors = {"pc-daniel": Collector(HASH, False), "off": Collector(HASH, True)}
        self.saved: list[Normalized] = []
        self.existing: set[UUID] = set()
        self.race = False

    def collector(self, collector_id: str) -> Collector | None:
        return self.collectors.get(collector_id)

    def batch_exists(self, batch_id: UUID) -> bool:
        return batch_id in self.existing

    def save(self, envelope: Envelope, normalized: Normalized) -> int:
        if self.race:
            raise DuplicateBatch
        self.saved.append(normalized)
        self.existing.add(envelope.batch_id)
        return len(normalized.rows)

    def ping(self) -> None:
        pass


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def client(store: FakeStore) -> TestClient:
    return TestClient(build_app(store))


def post(client: TestClient, body: Any = ENVELOPE, key: str | None = KEY) -> Any:
    headers = {"Content-Type": "application/json", "Content-Encoding": "gzip"}
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    return client.post(
        "/ingest/v1/batches", content=gzip.compress(json.dumps(body).encode()), headers=headers
    )


def test_accepts_a_gzipped_batch(client: TestClient, store: FakeStore) -> None:
    response = post(client)
    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "n_states": 1,
        "n_inserted": 1,
        "n_rejected": 0,
    }
    assert len(store.saved) == 1


def test_second_upload_is_a_duplicate_and_stores_nothing(
    client: TestClient, store: FakeStore
) -> None:
    post(client)
    response = post(client)
    assert (response.status_code, response.json()) == (200, {"status": "duplicate"})
    assert len(store.saved) == 1


def test_concurrent_upload_race_is_a_duplicate(client: TestClient, store: FakeStore) -> None:
    store.race = True
    assert post(client).status_code == 200


@pytest.mark.parametrize("key", [None, "wrong-key"])
def test_bad_key_is_401(client: TestClient, store: FakeStore, key: str | None) -> None:
    assert post(client, key=key).status_code == 401
    assert store.saved == []


@pytest.mark.parametrize("collector_id", ["off", "unknown", None])
def test_disabled_or_unknown_collector_is_401(client: TestClient, collector_id: Any) -> None:
    assert post(client, {**ENVELOPE, "collector_id": collector_id}).status_code == 401


def test_invalid_envelope_is_422(client: TestClient, store: FakeStore) -> None:
    assert post(client, {**ENVELOPE, "http_status": "nope"}).status_code == 422
    assert post(client, {**ENVELOPE, "response": {"states": []}}).status_code == 422
    assert store.saved == []


def test_garbage_body_is_422(client: TestClient) -> None:
    headers = {"Content-Encoding": "gzip", "Authorization": f"Bearer {KEY}"}
    response = client.post("/ingest/v1/batches", content=b"not gzip", headers=headers)
    assert response.status_code == 422


def test_oversized_decompressed_body_is_413(client: TestClient) -> None:
    body = {**ENVELOPE, "padding": "x" * 21_000_000}
    assert post(client, body).status_code == 413


def test_failed_opensky_request_is_stored(client: TestClient, store: FakeStore) -> None:
    response = post(client, {**ENVELOPE, "http_status": 429, "response": None})
    assert response.status_code == 202
    assert store.saved[0].rows == []


def test_healthz(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
