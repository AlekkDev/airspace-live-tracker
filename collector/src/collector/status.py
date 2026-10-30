"""`uv run -m collector status`: what is in the spool, newest batches last."""

import gzip
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BatchInfo:
    requested_at: str
    kind: str
    http_status: int
    rows: int
    credits_remaining: int | None


@dataclass(frozen=True)
class SpoolSummary:
    pending_files: int
    pending_bytes: int
    newest: list[BatchInfo]


def spool_summary(root: Path, newest: int = 5) -> SpoolSummary:
    files = sorted((root / "pending").glob("*.json.gz"))  # UUIDv7 names sort by time
    return SpoolSummary(
        pending_files=len(files),
        pending_bytes=sum(f.stat().st_size for f in files),
        newest=[_info(f) for f in files[-newest:]] if newest else [],
    )


def _info(path: Path) -> BatchInfo:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        env = json.load(f)
    response = env["response"]
    rows = len((response.get("states") if isinstance(response, dict) else response) or [])
    return BatchInfo(
        env["requested_at"],
        env["query"]["kind"],
        env["http_status"],
        rows,
        env["credits_remaining"],
    )


def format_summary(summary: SpoolSummary) -> str:
    lines = [f"pending: {summary.pending_files} files, {summary.pending_bytes / 1e6:.1f} MB"]
    for b in summary.newest:
        lines.append(
            f"  {b.requested_at}  {b.kind:<13} http {b.http_status:<3}  rows {b.rows:>6}"
            f"  credits left {b.credits_remaining}"
        )
    return "\n".join(lines)
