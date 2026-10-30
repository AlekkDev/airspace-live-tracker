from pathlib import Path

import pytest

from collector.lock import AlreadyRunning, single_instance


def test_second_instance_is_refused(tmp_path: Path) -> None:
    lock = tmp_path / "collector.lock"
    with single_instance(lock), pytest.raises(AlreadyRunning), single_instance(lock):
        pass


def test_lock_is_released_on_exit(tmp_path: Path) -> None:
    lock = tmp_path / "collector.lock"
    with single_instance(lock):
        pass
    with single_instance(lock):
        pass
