import gzip
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def read_pending() -> Callable[[Path], list[dict[str, Any]]]:
    def read(spool_dir: Path) -> list[dict[str, Any]]:
        out = []
        for path in sorted((spool_dir / "pending").glob("*.json.gz")):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                out.append(json.load(f))
        return out

    return read
