"""End-to-end check of ingest-api against the real schema. Runs inside the ingest-api container
(infra/test-db.sh), so it can use the service's own DATABASE_URL to listen for notifications."""

import gzip
import json
import os
import time
import urllib.error
import urllib.request
import uuid

import psycopg

URL = "http://127.0.0.1:8000/ingest/v1/batches"
KEY = os.environ["COLLECTOR_KEY"]
STATE = ["4B1805", "SWR283  ", "CH", 1793716288, 1793716289, 16.12, 48.02, 10363.2, False]
STATE += [231.4, 92.1, 0.0, None, 10500.0, "2331", False, 0, 4]
BAD_STATE = ["nothex", None, "CH", None, None, 16.12, 48.02, None, False]
BAD_STATE += [None, None, None, None, None, None, False, 0, 4]


def envelope(snapshot: int) -> dict:
    return {
        "batch_id": str(uuid.uuid4()),
        "collector_id": "smoke-01",
        "query": {"kind": "states_global", "extended": True},
        "requested_at": "2026-10-30T12:00:00.000Z",
        "http_status": 200,
        "retry_after_s": None,
        "credits_remaining": 3000,
        "response": {"time": snapshot, "states": [STATE, BAD_STATE]},
    }


def post(body: dict, key: str = KEY) -> tuple[int, dict]:
    request = urllib.request.Request(
        URL,
        data=gzip.compress(json.dumps(body).encode()),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def check(actual: object, expected: object, what: str) -> None:
    if actual != expected:
        raise SystemExit(f"FAILED {what}: expected {expected}, got {actual}")
    print(f"ok: {what}")


with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as listener:
    listener.execute("LISTEN new_snapshot")

    old = envelope(1793000000)
    status, body = post(old)
    check(status, 202, "old batch accepted")
    check(body["n_inserted"], 1, "good row stored")
    check(body["n_rejected"], 1, "bad row counted")
    check(post(old)[0], 200, "same batch again is a duplicate")
    check(post(old, key="wrong")[0], 401, "wrong key refused")
    check(list(listener.notifies(timeout=1, stop_after=1)), [], "old batch does not notify")

    live = envelope(int(time.time()))
    check(post(live)[0], 202, "live batch accepted")
    check(len(list(listener.notifies(timeout=5, stop_after=1))), 1, "live batch notifies")

    failed = {**envelope(0), "http_status": 429, "retry_after_s": 60, "response": None}
    check(post(failed)[0], 202, "failed OpenSky request stored")

    flights = {
        **envelope(0),
        "query": {
            "kind": "flights_all",
            "begin": "2026-10-29T00:00:00Z",
            "end": "2026-10-29T02:00:00Z",
        },
        "response": [{"icao24": "4B1805", "firstSeen": 1793000000, "lastSeen": 1793003000}],
    }
    check(post(flights)[1]["n_inserted"], 1, "flight list stored")
print("ingest smoke test passed")
