# ADR-0003 · PostgreSQL + TimescaleDB + PostGIS as the single live store

**Status:** accepted · 2026-10-27 · revised 2026-10-31

## Context
We need time-series storage (~11M rows/day), geospatial queries, relational joins with reference data, a read-only SQL surface for the LLM, and something cheap to run on one VM.

## Decision
One PostgreSQL 16 instance with TimescaleDB (hypertables, compression, continuous aggregates, retention) and PostGIS, using the `timescale/timescaledb-ha` image pinned to a TimescaleDB 2.19+ release. Dagster and MLflow keep their metadata in separate databases on the same instance. Older raw history stays in the collector's Parquet archives and is queried with DuckDB.

## Consequences
- One database to operate, back up and secure, and it speaks plain SQL, which suits the LLM and Grafana.
- Compression (~10×) and 90-day retention keep raw data at an estimated 30–35 GB; the VM has 200 GB ([01](../01-architecture.md#sizing)).
- TimescaleDB features we rely on (compression, continuous aggregates, policies) are not in the Apache-licensed build that managed clouds offer, so we self-host.
- Releases before the fix for timescale/timescaledb#7672 lose rows when inserting with `ON CONFLICT DO NOTHING` into compressed chunks; the pinned version and a CI test guard against it.
- Alternatives considered:
  - ClickHouse: faster analytics, but a second system with weaker geospatial and relational support.
  - Kafka + a data lake: unjustified at this scale.
  - Managed cloud Postgres: monthly cost and no Timescale compression.
