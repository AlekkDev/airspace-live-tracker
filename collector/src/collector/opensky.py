"""OpenSky REST client: OAuth2 client credentials, one GET per call
(docs/02-data-sources.md#opensky-network). Never raises for HTTP or network failures; the result
says what happened so every attempt can be spooled."""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
)
API_BASE = "https://opensky-network.org/api"
REQUEST_TIMEOUT_S = 20
REFRESH_MARGIN_S = 60

log = structlog.get_logger()


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class FetchResult:
    requested_at: datetime
    http_status: int  # OpenSky's status; 0 = timeout, network error, token failure or bad body
    retry_after_s: int | None
    credits_remaining: int | None
    body: Any  # parsed JSON for a 200, otherwise None


class TokenProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        client_id: str,
        client_secret: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._form = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        async with self._lock:
            if self._token is None or self._expires_at - self._clock() < REFRESH_MARGIN_S:
                self._token = await self._refresh()
            return self._token

    def invalidate(self) -> None:
        self._token = None

    async def _refresh(self) -> str:
        started = self._clock()
        try:
            resp = await self._client.post(TOKEN_URL, data=self._form, timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            payload = resp.json()
            token = str(payload["access_token"])
            self._expires_at = started + float(payload["expires_in"])
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise TokenError(type(exc).__name__) from exc
        return token


class OpenSky:
    def __init__(self, client: httpx.AsyncClient, tokens: TokenProvider) -> None:
        self._client = client
        self._tokens = tokens

    async def get(self, path: str, params: dict[str, Any]) -> FetchResult:
        try:
            token = await self._tokens.token()
        except TokenError as exc:
            log.warning("opensky_token_failed", error=str(exc))
            return FetchResult(datetime.now(UTC), 0, None, None, None)

        requested_at = datetime.now(UTC)
        try:
            resp = await self._client.get(
                f"{API_BASE}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=REQUEST_TIMEOUT_S,
            )
        except httpx.HTTPError as exc:
            log.warning("opensky_request_failed", path=path, error=type(exc).__name__)
            return FetchResult(requested_at, 0, None, None, None)

        retry_after = _int_header(resp, "X-Rate-Limit-Retry-After-Seconds")
        credits = _int_header(resp, "X-Rate-Limit-Remaining")
        if resp.status_code == 401:
            self._tokens.invalidate()
        if resp.status_code != 200:
            return FetchResult(requested_at, resp.status_code, retry_after, credits, None)
        try:
            body = resp.json()
        except ValueError:
            log.warning("opensky_bad_body", path=path)
            return FetchResult(requested_at, 0, retry_after, credits, None)
        return FetchResult(requested_at, 200, retry_after, credits, body)


def _int_header(resp: httpx.Response, name: str) -> int | None:
    value = resp.headers.get(name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None
