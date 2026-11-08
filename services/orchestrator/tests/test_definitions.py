from dagster import Definitions

from orchestrator.definitions import defs


def test_code_location_loads() -> None:
    assert isinstance(defs, Definitions)
    Definitions.validate_loadable(defs)
