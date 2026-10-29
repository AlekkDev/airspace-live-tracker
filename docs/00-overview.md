# 00 · Overview

## Purpose

1. **Course deliverable** for the MSc Cloud & AI project (8 weeks).
2. **Portfolio piece** for AI Engineer and Data Engineer applications. Every design choice must be explainable in an interview, and the result must be visible: a public URL, a demo video, dashboards, and a README with an architecture diagram.

## Scope: Level 1

Level 1 uses OpenSky's free API as the only live source. Everything below is Level 1. Our own ADS-B receiver (Level 2) is out of scope ([ADR-0002](adr/0002-source-agnostic-ingestion.md)).

### Core: must ship

| Feature | Description |
|---|---|
| Data collection | Two home collectors poll OpenSky every 90 s (offset 45 s), spool locally, upload, archive to R2; daily OpenSky flight lists |
| Live map | Dark world map; aircraft coloured by altitude, moving smoothly between snapshots |
| Unusual-traffic heatmap | H3 hexagons with unusually high or low traffic for that hour of the week (statistical v1) |
| Event feed | Emergency squawks, go-arounds, unusual-traffic start/end, collector gaps, data-quality failures |
| Arrival board | Predicted arrival times with a p10–p90 range for flights inbound to Vienna (LOWW), Bratislava (LZIB), Budapest (LHBP) |
| Destination estimate | Top-3 likely destinations from the route lookup, in the aircraft card |
| AI briefing | A short airspace summary every 30 min, written from database facts |
| AI chat | Plain-English question → SQL against curated views → answer, with the SQL shown |
| Dashboards | Public Grafana: ingestion, gaps, data quality, model results |

### Stretch: only after the core ships

Built in this order, only when the roadmap promotes them ([10](10-roadmap.md)):
1. Destination re-ranker (kinematic model on top of the route lookup).
2. Unusual-traffic v2 (STL or Isolation Forest).
3. Holding-pattern events.
4. Self-hosted map tiles (Protomaps PMTiles).

## Success criteria

- **Collection:** each collector misses fewer than 5% of its 90 s slots per week (`slot_coverage` over 7 days, [04](04-pipelines.md#data-quality-checks)), and every gap shows on the ops dashboard and in the event feed.
- **Map:** the public URL shows the live map in under 3 s and renders 10k+ aircraft at 60 fps on a laptop.
- **Unusual traffic:** the heatmap uses the hour-of-week baseline (≥ 3 weeks of collected data) and reports synthetic-injection recall and events per day in its model card.
- **ETA:** p50 MAE beats the historical-median baseline B1 on a time-based hold-out week ([06](06-ml.md#2--arrival-time-eta)).
- **Destination:** the route lookup reports top-1 / top-3 accuracy against the nearest-airport-ahead baseline.
- **Chat:** at least 80% execution accuracy on the 30+ question golden set, in CI.
- **Reproducible:** `docker compose -f infra/compose.yml -f infra/compose.dev.yml up` starts the backend with a seeded database on any machine, and each merge to `main` deploys it.
- **Presentable:** the README has an architecture diagram, a demo video and links to the live app and the public Grafana dashboards.

## Known limits of the data

These are permanent for Level 1. The product works around them and says so.

| Limit | Consequence | How we handle it |
|---|---|---|
| OpenSky sees only what its volunteer receivers hear | A receiver outage looks like a traffic drop | "Low" anomalies carry a coverage-gap caveat |
| No ground truth for unusual traffic | Can't measure accuracy directly | Synthetic injection + list of known real events |
| 45–90 s between snapshots | Landing times accurate to about a minute; short manoeuvres missed | ETAs as ranges; precision stated in the model card |
| Aircraft don't broadcast destinations | Destinations are estimates; diversions show late | Top-3 with probabilities, labelled "estimate" |
| No schedules or air-traffic-control data | Far-out ETAs can't foresee holding or runway changes | Wider p10–p90 ranges |
| 4,000 credits per account per day | No faster global polling | Two accounts on a 45 s offset (subject to OpenSky's terms) |
| Collection depends on home internet | Gaps happen | Shown openly; reduced by a dedicated low-power device |
| Text-to-SQL is never 100% correct | Some wrong answers | SQL always shown; 80% eval target |

## Non-goals

- Commercial use (the OpenSky licence forbids it).
- Mobile apps, user accounts, airline schedules or delay data.
- Detecting individual "unusual flights" (needs routes and schedules we don't have).
- Exactly-once streaming infrastructure (Kafka, Flink); our scale doesn't need it.

## Glossary

| Term | Meaning |
|---|---|
| State vector | One aircraft's position and velocity at one moment, as returned by OpenSky |
| Snapshot | One successful `/states/all` response: all state vectors at one OpenSky `time` |
| Live snapshot | A snapshot no older than 10 minutes |
| icao24 | 24-bit transponder address in lower-case hex, e.g. `4b1805`; the aircraft identity |
| Callsign | Flight identifier broadcast by the aircraft, e.g. `AUA123` |
| Squawk | 4-digit transponder code; 7500 hijack, 7600 radio failure, 7700 emergency |
| H3 | Uber's hexagonal grid; we use resolution 4 (~1,770 km² cells) |
| Hour of week | 0–167, Monday 00:00 UTC = 0 |
| Collector | Our program that polls OpenSky and ships batches to the server |
| Spool | The collector's local on-disk buffer of batches not yet confirmed by the server |
| Credits | OpenSky's daily API quota unit |
| Core / stretch | Must ship / built only after the core ships and the roadmap promotes it |
