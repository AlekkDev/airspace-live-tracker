from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from collector.opensky import FetchResult

REQUESTED_AT = datetime(2026, 11, 3, 6, 0, 1, tzinfo=UTC)

Respond = Callable[[str, dict[str, Any]], FetchResult]


class FakeOpenSky:
    """Stands in for collector.opensky.OpenSky; records calls and answers from `respond`."""

    def __init__(self, respond: Respond) -> None:
        self.respond = respond
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get(self, path: str, params: dict[str, Any]) -> FetchResult:
        self.calls.append((path, dict(params)))
        return self.respond(path, params)


def result(status: int, body: Any = None, retry_after: int | None = None) -> FetchResult:
    return FetchResult(REQUESTED_AT, status, retry_after, 3000, body)


def scripted(*results: FetchResult) -> Respond:
    queue = list(results)
    return lambda path, params: queue.pop(0)
