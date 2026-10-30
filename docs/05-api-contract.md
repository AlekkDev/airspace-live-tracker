# 05 · API contract

This is the boundary between backend and frontend work. Change it here first, then in code. FastAPI's generated spec at `/api/v1/openapi.json` must match this document.

- Base URLs: `https://api.<domain>/api/v1` (public), `https://ingest.<domain>/ingest/v1` (collectors). `<domain>` is open decision O5 ([10](10-roadmap.md#open-decisions)). While the project is private, collectors use `http://airspace-vm:8000/ingest/v1` over the tailnet, which encrypts the traffic ([D3](11-tasks.md#decided-while-building)).
- JSON, UTF-8. Timestamps are ISO-8601 UTC with `Z`. Units are SI.
- Errors: `{"error": {"code": "string", "message": "string"}}` with a matching HTTP status.
- **CORS** (public API only): allowed origins `https://<domain>` and `https://*.<pages-project>.pages.dev` (Cloudflare Pages previews); methods `GET, POST`; header `Content-Type`; no credentials.
- **Client IP:** the public API is reachable only through Cloudflare. It reads the client IP from `CF-Connecting-IP` and uses it only for rate limits, in memory. It is never stored.

## Public API

### `GET /live/snapshot`

The latest snapshot ([04](04-pipelines.md#shared-definitions)). Optional `bbox=minLon,minLat,maxLon,maxLat`. Optional `t=<snapshot_time>` requests that exact snapshot; responses with `t` are sent with `Cache-Control: public, max-age=86400, immutable`, responses without `t` with `Cache-Control: no-store`.

```json
{
  "snapshot_time": "2026-11-03T14:31:30Z",
  "next_expected_at": "2026-11-03T14:32:15Z",
  "fields": ["icao24","callsign","lon","lat","alt_m","vel_ms","track_deg","vrate_ms","on_ground","category","squawk","pos_age_s"],
  "states": [
    ["4b1805","SWR283",16.12,48.02,10363.2,231.4,92.1,0.0,false,4,"2331",2]
  ]
}
```

- `alt_m` is `baro_altitude_m` (pressure altitude), the value used for the altitude colour bands.
- `pos_age_s` = `snapshot_time − time_position` in whole seconds; `null` when `time_position` is null.
- States without lat/lon are omitted.
- `next_expected_at` = the latest snapshot's `snapshot_time` + 90 s.
- ~10k aircraft is about 650 KB, ~160 KB gzipped.

### `GET /live/stream` (Server-Sent Events)

| Event | Data | Sent when |
|---|---|---|
| `snapshot_ready` | `{"snapshot_time": "..."}` | `NOTIFY new_snapshot` (live snapshots only) |
| `event` | one event object, same shape as in `/events` | `NOTIFY new_event` (events with `ts` in the last 10 min) |

Keep-alive comment every 20 s. On `snapshot_ready` the client fetches `GET /live/snapshot?t=<snapshot_time>` (cacheable).

### `GET /aircraft/{icao24}`

```json
{
  "icao24": "4b1805", "callsign": "SWR283", "registration": "HB-JCA",
  "typecode": "BCS3", "operator": "Swiss", "airline": "Swiss International Air Lines",
  "last_state": { "time": "...", "lon": 16.12, "lat": 48.02, "alt_m": 10363, "vel_ms": 231, "track_deg": 92, "vrate_ms": 0, "pos_age_s": 2 },
  "flight": { "flight_id": "uuid", "first_seen": "...", "dep_icao": "LSZH", "dep_source": "opensky" },
  "destination": { "predicted_at": "...", "method": "route_lookup",
                   "candidates": [ {"icao":"LOWW","p":0.81}, {"icao":"LHBP","p":0.12}, {"icao":"LZIB","p":0.04} ] },
  "eta": { "airport_icao": "LOWW", "p10": "...", "p50": "...", "p90": "...", "model_version": "eta@7" }
}
```

`flight`, `destination` and `eta` may be `null`. 404 when the aircraft is not in the last 30 min of data.

### `GET /aircraft/{icao24}/track?minutes=60`

`{"icao24": "...", "points": [[unix_s, lon, lat, alt_m], ...]}`. `minutes` ∈ [1, 240], default 60. Points are distinct `(icao24, time_position)` positions in time order.

### `GET /anomalies?bucket=latest`

`bucket` is `latest` (the newest scored bucket) or an ISO bucket start.

```json
{ "bucket": "2026-11-03T14:15:00Z", "baseline_kind": "hour_of_week",
  "cells": [ {"h3":"841e15bffffffff","observed":42.1,"expected":28.0,"z":3.4,"direction":"high","persistent":true} ] }
```

H3 ids are hex strings. Only flagged cells are returned. `baseline_kind = cold_start` means the UI shows "baseline warming up".

### `GET /arrivals?airport=LOWW`

`airport` ∈ `LOWW | LZIB | LHBP`.

```json
{ "airport_icao": "LOWW", "generated_at": "...",
  "flights": [ { "icao24":"...", "callsign":"AUA92", "dep_icao":"LGAV",
                 "eta_p50":"...", "eta_p10":"...", "eta_p90":"...",
                 "distance_km": 182.4, "phase": "descent" } ] }
```

- One row per flight with an ETA prediction in the last 5 min, plus flights that landed (`arrived_at`) in the last 10 min.
- `phase`: `landed` if `arrived_at` is set; else `approach` if `distance_km ≤ 30`; else `descent` if the latest `vrate_ms ≤ −2`; else `cruise`.
- Sorted by `eta_p50`; landed flights last.

### `GET /events?limit=50&before_ts=<ISO>&before_id=<event_id>`

Ordered by `(ts, event_id)` descending. `limit` ∈ [1, 100]. For the next page pass the last item's `ts` and `event_id`, which the response repeats as `next_cursor` (`null` at the end).

```json
{ "events": [ { "event_id": 1, "ts": "...", "kind": "go_around", "severity": "warn",
                "title": "Go-around at LOWW (AUA478)", "icao24": "...", "airport_icao": "LOWW",
                "lon": 16.6, "lat": 48.1 } ],
  "next_cursor": { "before_ts": "...", "before_id": 1 } }
```

`lon`/`lat` are `null` for `collector_gap` and `dq_fail`.

### `GET /briefing/latest`

`{"generated_at":"...", "window_end":"...", "model":"claude-haiku-5-5", "content_md":"...", "next_at":"..."}`. Only briefings with `number_check = 'pass'` are served; otherwise the previous passing one is returned.

### `POST /chat`

Request: `{"question": "Which airline had the most arrivals into Vienna yesterday?"}`

```json
{ "answer_md": "**Austrian Airlines** with 214 arrivals ...",
  "sql": "SELECT airline_name, count(*) ...",
  "columns": ["airline_name","arrivals"], "rows": [["Austrian Airlines",214]],
  "latency_ms": 2140 }
```

| Limit | Value | Response when exceeded |
|---|---|---|
| Question length | 500 characters | 422 `question_too_long` |
| Rows returned | 200 | truncated silently |
| Per IP | 10 questions per rolling hour | 429 `rate_limited` |
| Global | 200 questions per UTC day | 429 `daily_cap_reached` |

The global count comes from `llm.chat_log`; the per-IP count is in public-api memory and resets on restart.

### `GET /stats`

`{"aircraft_now": 9412, "snapshot_time": "...", "collectors_online": 2, "rows_today": 8123456, "dq_status": "pass"}`

- `collectors_online`: collectors with a successful batch in the last 3 min.
- `rows_today`: sum of `n_inserted` for batches received since 00:00 UTC.
- `dq_status`: worst status among the latest result of each check.

### `GET /health`

`{"status":"ok","db":"ok","last_snapshot_age_s": 31}`. `status` is `degraded` when `last_snapshot_age_s > 300`.

## Ingest API

### `POST /ingest/v1/batches`

Headers: `Authorization: Bearer <collector key>`, `Content-Type: application/json`, `Content-Encoding: gzip`.

State vectors:

```json
{
  "batch_id": "0192f0c4-...",
  "collector_id": "pc-daniel",
  "query": { "kind": "states_global", "extended": true },
  "requested_at": "2026-11-03T14:31:30.120Z",
  "http_status": 200,
  "retry_after_s": null,
  "credits_remaining": 3120,
  "response": { "time": 1793716290, "states": [ ["4b1805","SWR283  ","Switzerland",1793716288,1793716289,16.12,48.02,10363.2,false,231.4,92.1,0.0,null,10500.0,"2331",false,0,4] ] }
}
```

Flight list (one two-hour window):

```json
{
  "batch_id": "0192f0c5-...",
  "collector_id": "pc-daniel",
  "query": { "kind": "flights_all", "begin": "2026-11-02T00:00:00Z", "end": "2026-11-02T02:00:00Z" },
  "requested_at": "2026-11-03T06:00:04.512Z",
  "http_status": 200,
  "retry_after_s": null,
  "credits_remaining": 3640,
  "response": [ { "icao24": "4b1805", "firstSeen": 1793577600, "estDepartureAirport": "LSZH", "lastSeen": 1793581800,
                  "estArrivalAirport": "LOWW", "callsign": "SWR283  ", "estDepartureAirportHorizDistance": 1200,
                  "estDepartureAirportVertDistance": 40, "estArrivalAirportHorizDistance": 900,
                  "estArrivalAirportVertDistance": 30, "departureAirportCandidatesCount": 1, "arrivalAirportCandidatesCount": 2 } ]
}
```

- `response` is OpenSky's body passed through unchanged; the server does all normalisation.
- When the OpenSky request failed, `http_status` is its status (`0` for timeout or network error) and `response` is `null`. These batches are stored so gaps are explained.

| Status | Body | Collector action |
|---|---|---|
| 202 | `{"status":"accepted","n_states":9412,"n_inserted":9412,"n_rejected":0}` | move to `spool/sent/` |
| 200 | `{"status":"duplicate"}` | move to `spool/sent/` |
| 401 | error | stop uploading, see [04](04-pipelines.md#p1--collector) |
| 413 | error (body > 20 MB) | move to `spool/rejected/` |
| 422 | error (invalid envelope) | move to `spool/rejected/` |
| 5xx | error | retry with backoff |
