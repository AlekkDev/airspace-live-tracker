# ADR-0002 · Source-agnostic ingestion

**Status:** accepted · 2026-10-27

## Context
Level 2 adds our own ADS-B receiver (1 Hz, regional) next to the OpenSky API (90 s, global). We don't want to rebuild the pipeline when it arrives.

## Decision
Every source is converted to the same state-vector shape and goes through the same `POST /ingest/v1/batches` contract. Rows carry a `source` column (`opensky_api`, `local_adsb`). Collectors register with a `source` in `ops.collectors`. Raw upstream payloads are passed through unchanged; normalisation happens only on the server.

## Consequences
- Level 2 needs a new collector adapter, a dedupe preference (local over API for the same `icao24` and second), and a faster SSE path for the receiver's region. Schemas, jobs and models stay as they are.
- `raw.state_vectors` grows faster with a 1 Hz source. Level 2 will downsample local data to 5 s before storage, with the full rate kept only in the collector's Parquet archive.
