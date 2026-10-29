# ADR-0002 · Level 2 (own ADS-B receiver) is out of scope

**Status:** accepted · 2026-10-27 · revised 2026-10-29

## Context
A later Level 2 could add our own ADS-B receiver (Raspberry Pi + RTL-SDR, 1 Hz, regional) next to the OpenSky API. The first version of this ADR claimed Level 2 would only "add a source" with schemas, jobs and models unchanged. That does not hold:
- The receiver's decoder output is not OpenSky's payload, so it needs its own adapter.
- With the `(icao24, snapshot_time)` primary key and `ON CONFLICT DO NOTHING`, whichever row arrives first wins; preferring local data needs a schema and ingest change.
- A 1 Hz map cannot be served from storage that keeps local data at 5 s.
- Mixing a regional 1 Hz source into `raw.state_vectors` would break the density normalisation of the unusual-traffic model.

## Decision
Level 1 ships with OpenSky as the only live source. The ingest contract stays OpenSky-specific (`query.kind` = `states_global` or `flights_all`). Level 2 is not designed or built during the course.

## Consequences
- No `source` column or Level 2 code paths in Level 1; nothing to keep half-working.
- If Level 2 is picked up later, it gets its own ADR covering: a separate table or `source` column with a preference rule, a separate live path for 1 Hz data outside Postgres, and excluding local data from density.
- A feeder account would double the `/states/*` credits to 8,000/day; that benefit is noted but not planned for.
