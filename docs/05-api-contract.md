# 05 · API contract

This is the boundary between backend and frontend work. Change it here first, then in code. FastAPI's generated OpenAPI spec at `/api/v1/openapi.json` must match this doc.

- Base URLs: `https://api.<domain>/api/v1` (public), `https://ingest.<domain>/ingest/v1` (collectors).
- JSON, UTF-8, ISO-8601 UTC timestamps, SI units.
- Errors: `{"error": {"code": "string", "message": "string"}}` with a matching HTTP status.

## Public API

### `GET /live/snapshot`
The latest merged snapshot. Optional `bbox=minLon,minLat,maxLon,maxLat`.

The array format keeps payloads small: ~10k aircraft is about 600 KB, or ~150 KB gzipped.

```json
{
  "snapshot_time": "2026-11-03T14:31:30Z",
  "next_expected_at": "2026-11-03T14:32:15Z",
  "fields": ["icao24","callsign","lon","lat","alt_m","vel_ms","track_deg","vrate_ms","on_ground","category","squawk"],
  "states": [
    ["4b1805","SWR283",16.12,48.02,10363.2,231.4,92.1,0.0,false,3,"2331"]
  ]
}
```

### `GET /live/stream` (Server-Sent Events)
Event `snapshot` with the same body as above when a new snapshot is ingested. Event `event` with one `core.events` row. Keep-alive comment every 20 s.

### `GET /aircraft/{icao24}`
```json
{
  "icao24": "4b1805", "callsign": "SWR283", "registration": "HB-JCA",
  "typecode": "BCS3", "operator": "Swiss",
  "last_state": { "time": "...", "lon": 16.12, "lat": 48.02, "alt_m": 10363, "vel_ms": 231, "track_deg": 92, "vrate_ms": 0 },
  "flight": { "flight_id": "uuid", "first_seen": "...", "dep_icao": "LSZH" },
  "destination": { "predicted_at": "...", "candidates": [ {"icao":"LOWW","p":0.81}, {"icao":"LHBP","p":0.12}, {"icao":"LZIB","p":0.04} ] },
  "eta": { "airport_icao": "LOWW", "p10": "...", "p50": "...", "p90": "...", "model_version": "eta@v7" }
}
```
`destination` and `eta` may be `null`.

### `GET /aircraft/{icao24}/track?minutes=60`
`{"icao24": "...", "points": [[unix_s, lon, lat, alt_m], ...]}`. Max 240 minutes.

### `GET /anomalies?bucket=latest`
```json
{ "bucket": "2026-11-03T14:15:00Z",
  "cells": [ {"h3":"841e15bffffffff","observed":42.1,"expected":28.0,"z":3.4,"direction":"high"} ] }
```
H3 ids are returned as hex strings (deck.gl's `H3HexagonLayer` takes them directly).

### `GET /arrivals?airport=LOWW`
```json
{ "airport_icao": "LOWW", "generated_at": "...",
  "flights": [ { "icao24":"...", "callsign":"AUA92", "origin_icao":"LGAV",
                 "eta_p50":"...", "eta_p10":"...", "eta_p90":"...",
                 "distance_km": 182.4, "phase": "descent" } ] }
```
`phase` ∈ `cruise | descent | approach | landed`.

### `GET /events?limit=50&before=<event_id>`
`{"events": [{"event_id":1, "ts":"...", "kind":"go_around", "severity":"warn", "title":"Go-around at LOWW (AUA478)", "icao24":"...", "lon":16.6, "lat":48.1}]}`

### `GET /briefing/latest`
`{"generated_at":"...", "model":"claude-haiku-5-5", "content_md":"...", "next_at":"..."}`

### `POST /chat`
Request: `{"question": "Which airline had the most flights into Vienna yesterday?"}`
Response:
```json
{ "answer_md": "**Austrian Airlines** with 214 arrivals ...",
  "sql": "SELECT operator, count(*) ...",
  "columns": ["operator","arrivals"], "rows": [["Austrian",214]],
  "latency_ms": 2140 }
```
Limits: 500 characters per question, 200 rows returned, 10 questions per IP per hour, global daily cap.

### `GET /stats`
`{"aircraft_now": 9412, "snapshot_time": "...", "collectors_online": 2, "rows_today": 8123456, "dq_status": "pass"}`

### `GET /health`
`{"status":"ok","db":"ok","last_snapshot_age_s": 31}`

## Ingest API

### `POST /ingest/v1/batches`
Headers: `Authorization: Bearer <collector key>`, `Content-Encoding: gzip`.
```json
{
  "batch_id": "0192f0c4-...",
  "collector_id": "pc-daniel",
  "source": "opensky_api",
  "query": { "kind": "global", "bbox": null, "extended": true },
  "requested_at": "2026-11-03T14:31:30.120Z",
  "http_status": 200,
  "credits_remaining": 3120,
  "response": { "time": 1793716290, "states": [ ["4b1805","SWR283  ","Switzerland",1793716288,1793716289,16.12,48.02,10363.2,false,231.4,92.1,0.0,null,10500.0,"2331",false,0,3] ] }
}
```
`response.states` is passed through **unchanged** from OpenSky, so the server owns all normalisation.

| Status | Body | Meaning |
|---|---|---|
| 202 | `{"status":"accepted","n_states":9412,"n_inserted":9412}` | stored |
| 200 | `{"status":"duplicate"}` | `batch_id` already stored; collector treats it as success |
| 401 | error | bad key |
| 422 | error | invalid envelope; collector moves the file to `spool/rejected/` |

Failed requests from OpenSky (`http_status` ≠ 200, `response` = null) are still sent so gaps are explained in `ops.ingest_batches`.
