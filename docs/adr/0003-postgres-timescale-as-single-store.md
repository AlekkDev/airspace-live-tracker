# ADR-0003 · PostgreSQL + TimescaleDB + PostGIS as the single live store

**Status:** accepted · 2026-10-27

## Context
We need time-series storage (~10M rows/day), geospatial queries, relational joins with reference data, a read-only SQL surface for the LLM, and something cheap to run on one VPS.

## Decision
One PostgreSQL 16 instance with TimescaleDB (hypertables, compression, continuous aggregates, retention) and PostGIS. Historical Zenodo data stays in Parquet and is queried with DuckDB at training time.

## Consequences
- One database to operate, back up and secure, and it speaks plain SQL, which suits the LLM and Grafana.
- Compression (~10×) and 90-day retention keep disk usage under ~15 GB.
- Alternatives considered:
  - ClickHouse: faster analytics, but a second system plus weaker geospatial/relational support.
  - Kafka + a data lake: unjustified at this scale.
  - Managed cloud DB: monthly cost.
