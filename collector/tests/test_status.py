from datetime import UTC, datetime
from pathlib import Path

from collector.spool import Spool, make_envelope
from collector.status import spool_summary


def spool_one(spool: Spool, kind: str, status: int, response: object) -> None:
    spool.write(
        make_envelope(
            collector_id="pc-daniel",
            query={"kind": kind},
            requested_at=datetime(2026, 11, 3, 6, tzinfo=UTC),
            http_status=status,
            retry_after_s=None,
            credits_remaining=3000,
            response=response,
        )
    )


def test_summary_counts_pending_files_and_lists_the_newest(tmp_path: Path) -> None:
    spool = Spool(tmp_path)
    spool_one(spool, "states_global", 200, {"time": 1, "states": [["a"], ["b"]]})
    spool_one(spool, "states_global", 0, None)
    spool_one(spool, "flights_all", 200, [{"icao24": "a"}])

    summary = spool_summary(tmp_path, newest=2)

    assert summary.pending_files == 3
    assert summary.pending_bytes > 0
    assert [(b.kind, b.http_status, b.rows) for b in summary.newest] == [
        ("states_global", 0, 0),
        ("flights_all", 200, 1),
    ]
