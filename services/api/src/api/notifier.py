"""Bridge from Postgres `LISTEN`/`NOTIFY` to the SSE stream (`docs/05-api-contract.md`).

The listener is deliberately **synchronous, in a worker thread**, rather than an
`AsyncConnection`:

* psycopg's async mode refuses to run on Windows' default `ProactorEventLoop`
  (`Psycopg cannot use the 'ProactorEventLoop' to run in async mode`), and the loop is chosen
  by uvicorn, not by this module. A thread works on every platform.
* `LISTEN` is per-connection state held by the server, so a pooled connection would stop
  receiving as soon as it went back to the pool. One connection lives as long as one stream.
"""

import threading
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

import psycopg

# Channels already published by the database: docs/04-pipelines.md#p2--ingest and
# docs/03-data-model.md (the `core.events` trigger).
SNAPSHOT_CHANNEL = "new_snapshot"
EVENT_CHANNEL = "new_event"

# How long the listener blocks before checking whether the stream has closed.
POLL_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class Notify:
    """One `NOTIFY`: the channel name and its payload string."""

    channel: str
    payload: str


class Notifier(Protocol):
    """A blocking source of notifications. Tests replace it with a list."""

    def listen(self, stop: threading.Event) -> Iterator[Notify]:
        """Yield notifications until `stop` is set."""
        ...


class PgNotifier:
    """Opens one `LISTEN` connection per stream, in a worker thread."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def listen(self, stop: threading.Event) -> Iterator[Notify]:
        with psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(f"LISTEN {SNAPSHOT_CHANNEL}")
            conn.execute(f"LISTEN {EVENT_CHANNEL}")
            while not stop.is_set():
                for notify in conn.notifies(timeout=POLL_SECONDS):
                    yield Notify(channel=notify.channel, payload=notify.payload or "")
