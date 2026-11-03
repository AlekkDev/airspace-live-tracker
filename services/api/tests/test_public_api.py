from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.app import build_app
from api.models import FIELDS, Snapshot, StateRow
from api.store import Bbox

T = datetime(2026, 11, 3, 13, 26, 58, tzinfo=UTC)


def row(**overrides: Any) -> StateRow:
    values: dict[str, Any] = {
        "icao24": "4b1805",
        "callsign": "SWR283",
        "lon": 16.12,
        "lat": 48.02,
        "alt_m": 10363.2,
        "vel_ms": 231.4,
        "track_deg": 92.1,
        "vrate_ms": 0.0,
        "on_ground": False,
        "category": 4,
        "squawk": "2331",
        "pos_age_s": 2,
    }
    values.update(overrides)
    return StateRow(**values)


class FakeStore:
    def __init__(self) -> None:
        self.snapshot_time: datetime | None = T
        self.states: tuple[StateRow, ...] = (
            row(),
            row(icao24="4400aa", callsign=None, squawk=None, pos_age_s=None),
        )
        self.calls: list[tuple[datetime | None, Bbox | None]] = []
        self.fail = False

    def snapshot(self, at: datetime | None = None, bbox: Bbox | None = None) -> Snapshot | None:
        if self.fail:
            raise RuntimeError("database is down")
        self.calls.append((at, bbox))
        if self.snapshot_time is None or (at is not None and at != self.snapshot_time):
            return None
        return Snapshot(self.snapshot_time, self.states)

    def last_snapshot_time(self) -> datetime | None:
        if self.fail:
            raise RuntimeError("database is down")
        return self.snapshot_time

    def ping(self) -> None:
        pass


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def client(store: FakeStore) -> TestClient:
    return TestClient(build_app(store))


def test_snapshot_matches_the_contract(client: TestClient) -> None:
    response = client.get("/api/v1/live/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_time"] == "2026-11-03T13:26:58Z"
    assert body["next_expected_at"] == "2026-11-03T13:28:28Z"
    assert body["fields"] == list(FIELDS)
    assert body["states"][0] == [
        "4b1805",
        "SWR283",
        16.12,
        48.02,
        10363.2,
        231.4,
        92.1,
        0.0,
        False,
        4,
        "2331",
        2,
    ]
    # absent values stay null, and are not dropped from the array
    assert body["states"][1][1] is None
    assert body["states"][1][11] is None


def test_latest_snapshot_is_not_cached(client: TestClient) -> None:
    assert client.get("/api/v1/live/snapshot").headers["cache-control"] == "no-store"


def test_explicit_snapshot_is_immutable(client: TestClient) -> None:
    response = client.get("/api/v1/live/snapshot", params={"t": "2026-11-03T13:26:58Z"})

    assert response.status_code == 200
    assert response.json()["snapshot_time"] == "2026-11-03T13:26:58Z"
    assert response.headers["cache-control"] == "public, max-age=86400, immutable"


def test_bbox_is_passed_through(client: TestClient, store: FakeStore) -> None:
    response = client.get("/api/v1/live/snapshot", params={"bbox": "10.5,40,20,50.25"})

    assert response.status_code == 200
    assert store.calls == [(None, (10.5, 40.0, 20.0, 50.25))]


@pytest.mark.parametrize(
    "bbox",
    ["1,2,3", "1,2,3,4,5", "a,b,c,d", "10,40,5,50", "10,-95,20,50", "-181,0,20,50"],
)
def test_invalid_bbox_is_rejected(client: TestClient, bbox: str) -> None:
    response = client.get("/api/v1/live/snapshot", params={"bbox": bbox})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_bbox"
    assert client.get("/api/v1/live/snapshot").status_code == 200


@pytest.mark.parametrize("t", ["yesterday", "2026-11-03T13:26:58", "2026-13-03T13:26:58Z"])
def test_invalid_timestamp_is_rejected(client: TestClient, t: str) -> None:
    response = client.get("/api/v1/live/snapshot", params={"t": t})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_timestamp"


def test_unknown_snapshot_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/live/snapshot", params={"t": "2026-11-01T00:00:00Z"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "snapshot_not_found"


def test_no_live_data_is_503(client: TestClient, store: FakeStore) -> None:
    store.snapshot_time = None

    response = client.get("/api/v1/live/snapshot")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "no_live_data"


def test_health_ok(client: TestClient, store: FakeStore) -> None:
    store.snapshot_time = datetime.now(UTC) - timedelta(seconds=30)

    body = client.get("/api/v1/health").json()

    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert 25 <= body["last_snapshot_age_s"] <= 120


def test_health_degraded_when_stale(client: TestClient, store: FakeStore) -> None:
    store.snapshot_time = datetime.now(UTC) - timedelta(seconds=900)

    body = client.get("/api/v1/health").json()

    assert body["status"] == "degraded"
    assert body["db"] == "ok"


def test_database_failure_is_reported(client: TestClient, store: FakeStore) -> None:
    store.fail = True

    snapshot = client.get("/api/v1/live/snapshot")
    health = client.get("/api/v1/health")

    assert snapshot.status_code == 503
    assert snapshot.json()["error"]["code"] == "database_unavailable"
    assert health.status_code == 503
    assert health.json() == {"status": "degraded", "db": "error", "last_snapshot_age_s": None}
