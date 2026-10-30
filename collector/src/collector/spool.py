"""Local on-disk buffer of batches (docs/04-pipelines.md#p1--collector).

A batch is safe once `Spool.write` returns: the file is written to `.tmp`, flushed to disk and
renamed into `pending/`.
"""

import gzip
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from uuid6 import uuid7

from airspace_common.timefmt import iso_z

DIRS = ("pending", "sent", "rejected", "archive", "state")


def make_envelope(
    *,
    collector_id: str,
    query: dict[str, Any],
    requested_at: datetime,
    http_status: int,
    retry_after_s: int | None,
    credits_remaining: int | None,
    response: Any,
) -> dict[str, Any]:
    """Batch envelope of docs/05-api-contract.md#post-ingestv1batches."""
    return {
        "batch_id": str(uuid7()),
        "collector_id": collector_id,
        "query": query,
        "requested_at": iso_z(requested_at),
        "http_status": http_status,
        "retry_after_s": retry_after_s,
        "credits_remaining": credits_remaining,
        "response": response,
    }


class Spool:
    def __init__(self, root: Path) -> None:
        self.root = root
        for name in DIRS:
            (root / name).mkdir(parents=True, exist_ok=True)

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    def write(self, envelope: dict[str, Any]) -> Path:
        final = self.root / "pending" / f"{envelope['batch_id']}.json.gz"
        write_atomic(final, gzip.compress(json.dumps(envelope, separators=(",", ":")).encode()))
        return final


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
