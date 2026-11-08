"""The Dagster code location `airspace`, served by the dagster-code container.

Jobs and schedules from docs/04-pipelines.md#p4--orchestrated-jobs are added here as each
milestone builds them.
"""

from dagster import Definitions

defs = Definitions()
