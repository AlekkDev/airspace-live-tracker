import asyncio
import json
from collections.abc import Callable

import httpx

from collector.opensky import API_BASE, TOKEN_URL, OpenSky, TokenProvider


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def build(
    api: Callable[[httpx.Request], httpx.Response],
    token_status: int = 200,
    clock: Clock | None = None,
) -> tuple[OpenSky, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if str(request.url) == TOKEN_URL:
            if token_status != 200:
                return httpx.Response(token_status)
            return httpx.Response(200, json={"access_token": f"tok{len(seen)}", "expires_in": 1800})
        return api(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tokens = TokenProvider(client, "cid", "csecret", clock=clock or Clock())
    return OpenSky(client, tokens), seen


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"time": 1, "states": []}, headers={"X-Rate-Limit-Remaining": "3120"}
    )


def test_success_returns_body_and_remaining_credits() -> None:
    opensky, seen = build(ok)
    result = asyncio.run(opensky.get("/states/all", {"extended": 1}))
    assert result.http_status == 200
    assert result.body == {"time": 1, "states": []}
    assert result.credits_remaining == 3120
    api_call = seen[-1]
    assert str(api_call.url) == f"{API_BASE}/states/all?extended=1"
    assert api_call.headers["Authorization"] == "Bearer tok1"


def test_token_request_uses_client_credentials() -> None:
    opensky, seen = build(ok)
    asyncio.run(opensky.get("/states/all", {}))
    form = dict(x.split("=") for x in seen[0].content.decode().split("&"))
    assert form == {
        "grant_type": "client_credentials",
        "client_id": "cid",
        "client_secret": "csecret",
    }


def test_token_is_reused_until_60_seconds_before_expiry() -> None:
    clock = Clock()
    opensky, seen = build(ok, clock=clock)

    async def three_calls() -> None:
        await opensky.get("/states/all", {})
        clock.t = 1700.0  # 100 s left: reuse
        await opensky.get("/states/all", {})
        clock.t = 1750.0  # 50 s left: refresh
        await opensky.get("/states/all", {})

    asyncio.run(three_calls())
    token_calls = [r for r in seen if str(r.url) == TOKEN_URL]
    assert len(token_calls) == 2


def test_429_reports_retry_after() -> None:
    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"X-Rate-Limit-Retry-After-Seconds": "600"})

    opensky, _ = build(limited)
    result = asyncio.run(opensky.get("/states/all", {}))
    assert (result.http_status, result.retry_after_s, result.body) == (429, 600, None)


def test_timeout_is_status_0() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    opensky, _ = build(slow)
    assert asyncio.run(opensky.get("/states/all", {})).http_status == 0


def test_failed_token_refresh_is_status_0_without_calling_the_api() -> None:
    opensky, seen = build(ok, token_status=401)
    result = asyncio.run(opensky.get("/states/all", {}))
    assert result.http_status == 0
    assert all(str(r.url) == TOKEN_URL for r in seen)


def test_invalid_json_on_200_is_status_0() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>")

    opensky, _ = build(broken)
    result = asyncio.run(opensky.get("/states/all", {}))
    assert (result.http_status, result.body) == (0, None)


def test_api_401_forces_a_new_token_next_time() -> None:
    calls = {"n": 0}

    def first_401(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401) if calls["n"] == 1 else ok(request)

    opensky, seen = build(first_401)

    async def two_calls() -> None:
        await opensky.get("/states/all", {})
        await opensky.get("/states/all", {})

    asyncio.run(two_calls())
    assert len([r for r in seen if str(r.url) == TOKEN_URL]) == 2


def test_body_is_passed_through_unchanged() -> None:
    raw = {"time": 5, "states": [["4b1805", "SWR283  ", "Switzerland"]]}

    def body(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(raw).encode())

    opensky, _ = build(body)
    assert asyncio.run(opensky.get("/states/all", {})).body == raw
