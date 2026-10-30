"""One collector per spool. A second process (e.g. a manual run next to the scheduled task) would
poll in the same slots and double credit use, so it is refused."""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO


class AlreadyRunning(Exception):
    pass


@contextmanager
def single_instance(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as f:
        try:
            _lock(f)
        except OSError as exc:
            raise AlreadyRunning(f"another collector holds {path}") from exc
        try:
            yield
        finally:
            _unlock(f)


if sys.platform == "win32":
    import msvcrt

    def _lock(f: BinaryIO) -> None:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(f: BinaryIO) -> None:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(f: BinaryIO) -> None:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(f: BinaryIO) -> None:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
