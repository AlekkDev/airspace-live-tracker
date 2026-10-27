# 00 · Overview

## Purpose

1. **Course deliverable** for the MSc Cloud & AI project.
2. **Portfolio piece** for AI Engineer and Data Engineer applications. Every design choice should be something we can explain in an interview, and the result must be *visible*: a public URL, a demo video, dashboards, and a README with an architecture diagram.

## What we build

| Feature | Description |
|---|---|
| Live map | Dark world map; aircraft coloured by altitude, moving smoothly between 90 s snapshots (dead reckoning) |
| Anomaly heatmap | H3 hexagons that have unusually high or low traffic for that hour of the week |
| Event feed | Emergency squawks, go-arounds, holding patterns, anomaly start/end, collector outages |
| Arrival board | Predicted arrival times (with uncertainty) for flights inbound to Vienna (LOWW), Bratislava (LZIB), Budapest (LHBP) |
| Destination prediction | Top-3 likely destinations for any airborne flight |
| AI briefing | A short airspace summary regenerated every 30 min from database facts |
| AI chat | Plain-English questions → SQL against curated views → answer, with the SQL shown |
| Ops dashboards | Public Grafana: ingestion lag, rows/min, gaps, data-quality checks |

## Levels

| | Level 1 (now) | Level 2 (later) |
|---|---|---|
| Live data | OpenSky REST API, polled by collectors on our home PCs | Plus our own ADS-B receiver (Raspberry Pi + RTL-SDR + 1090 MHz antenna) |
| Refresh | ~45–90 s globally | ~1 s within ~250–400 km of the antenna |
| Collector host | Two Windows PCs (one per teammate), later a Raspberry Pi | Raspberry Pi (also feeds OpenSky, which doubles our API credits) |
| Cost | ~€10–15/month | + ~€150 one-time hardware |

Level 1 is designed so Level 2 only **adds a source**. The data model and API stay the same (see [ADR-0002](adr/0002-source-agnostic-ingestion.md)).

## Success criteria (Level 1)

- Collection runs continuously with less than 5% of 90 s slots missed per week, and any gaps show on the ops dashboard.
- The public URL loads the live map in under 3 s and renders 10k+ aircraft at 60 fps on a laptop.
- The anomaly heatmap uses at least 3 weeks of collected data.
- ETA model beats the `distance / groundspeed` baseline on MAE (minutes), evaluated on a time-based hold-out.
- Destination model reports top-1 / top-3 accuracy against a callsign-prior baseline.
- The chat answers at least 80% of a 30-question golden set correctly, and that eval runs in CI.
- `docker compose up` reproduces the backend on any machine, and each merge to `main` deploys it.
- The README has an architecture diagram, a demo GIF/video and links to the live app, Grafana and MLflow.

## Non-goals

- Commercial use (the OpenSky licence forbids it).
- Mobile apps, user accounts, flight schedules or airline delay data.
- Exactly-once streaming infrastructure (Kafka, Flink). Our scale doesn't need it, and we document why.

## Glossary

| Term | Meaning |
|---|---|
| State vector | One aircraft's position/velocity at one moment, as returned by OpenSky |
| Snapshot | One API response: all state vectors at one `time` |
| icao24 | 24-bit transponder address in hex, e.g. `4b1805`; the aircraft identity |
| Callsign | Flight identifier broadcast by the aircraft, e.g. `AUA123` |
| Squawk | 4-digit transponder code; 7500 hijack, 7600 radio failure, 7700 emergency |
| H3 | Uber's hexagonal grid; we use resolution 4 (~1,770 km² cells) for traffic density |
| Hour of week | 0–167, Monday 00:00 UTC = 0; the seasonality key for anomalies |
| Collector | Our program that polls OpenSky and ships snapshots to the server |
| Spool | The collector's local on-disk buffer of snapshots not yet confirmed by the server |
| Credits | OpenSky's daily API quota unit |
