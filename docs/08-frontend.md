# 08 · Frontend

The interactive mockup (mock data, design reference) is linked in [10 Roadmap](10-roadmap.md#links). Where the mockup and this document differ, this document wins.

## Stack

React 19 + TypeScript (strict) + Vite, MapLibre GL JS (basemap), deck.gl via `MapboxOverlay` (data layers), TanStack Query (REST), native `EventSource` (SSE), Tailwind CSS. Node 24 LTS, pnpm. Hosted on Cloudflare Pages.

Basemap: CARTO *Dark Matter* (free for non-commercial use, with attribution). Self-hosted Protomaps PMTiles is a stretch item.

## Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ◆ Airspace Monitor 9,412 aircraft · snapshot 34 s ago · collector online │
├───────────────────────────────────────────────┬──────────────────────────┤
│  [Aircraft] [Anomalies] [Airports]  layers    │ Briefing │ Ask │ Arrivals │ Events │
│                                               │                          │
│               MAP (deck.gl)                   │   tab content            │
│                                               │                          │
│  ┌ selected aircraft card ┐                   │                          │
│  └────────────────────────┘   altitude legend │                          │
├───────────────────────────────────────────────┴──────────────────────────┤
│ Data: The OpenSky Network · Map © CARTO © OpenStreetMap                  │
└──────────────────────────────────────────────────────────────────────────┘
```

At widths under 900 px the side panel becomes a bottom sheet. The attribution footer is always visible.

## Data flow

1. On load: `GET /live/snapshot`, then open `/live/stream`.
2. On `snapshot_ready`: `GET /live/snapshot?t=<snapshot_time>` (cacheable), then update positions.
3. On `event`: prepend to the Events feed and pulse the location if it has one.
4. If the stream disconnects, `EventSource` reconnects; on reconnect the client fetches `/live/snapshot` once.

## Map layers (deck.gl)

| Layer | deck.gl class | Data | Notes |
|---|---|---|---|
| Aircraft | `IconLayer` | `/live/snapshot` | Plane glyph rotated by `track_deg`, coloured by altitude band, pickable |
| Selected trail | `PathLayer` | `/aircraft/{icao24}/track` | Altitude-band colour per segment |
| Anomaly heatmap | `H3HexagonLayer` | `/anomalies` | Fill `--anom-high` / `--anom-low`; opacity `min(0.15 + 0.1·|z|, 0.6)`; non-persistent cells drawn with a dashed outline |
| Airports | `ScatterplotLayer` + `TextLayer` | static `airports.json` built from `ref.airports` | Target airports labelled |
| Event pulses | `ScatterplotLayer` (animated radius) | SSE `event` with a location | 10 s ring in `--accent` |

## Smooth motion between snapshots

Per aircraft keep `{lon, lat, vel_ms, track_deg, t0}`, where `t0 = snapshot_time − pos_age_s`. On each animation frame:
- `Δt = min(now − t0, 120 s)`.
- Advance the position along `track_deg` by `vel_ms · Δt` (flat-earth step).
- Do not extrapolate aircraft that are on the ground, have `vel_ms < 30`, or have `pos_age_s > 60`; draw stale ones (`pos_age_s > 60`) at 50% opacity.
- When a new snapshot arrives, ease each aircraft from its extrapolated position to the reported one over 1.5 s.
- Aircraft missing from 2 consecutive snapshots fade out.

## Visual spec

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0b1020` | page / ocean |
| `--land` | `#151d33` | basemap land (style override) |
| `--panel` | `#111a2e` | side panel, cards |
| `--border` | `#22304f` | dividers |
| `--text` | `#e7ecf6` | primary text |
| `--muted` | `#9aa8c2` | secondary text (≥ 4.5:1 on panel) |
| `--accent` | `#4cc3ff` | selection, links, focus, event pulses |
| `--warn` | `#ffb547` | warning badges in panels only, never on the map |
| `--alert` | `#ff6b6b` | emergency badges in panels only |
| `--anom-high` | `#c49bff` | more traffic than usual |
| `--anom-low` | `#3d6fd9` | less traffic than usual |

**Altitude bands** (aircraft and trail colour). A sequential light-to-dark ramp, so bands differ in lightness for colour-blind viewers, and no band reuses a UI or anomaly colour:

| Band (`alt_m`) | Colour |
|---|---|
| on ground | `#7d8799` |
| < 3,000 m (≈ FL100) | `#fff1a8` |
| 3,000–7,000 m | `#f2b84b` |
| 7,000–10,000 m | `#e0703a` |
| > 10,000 m | `#c0447a` |

The selected aircraft gets a 2 px `--accent` halo.

Typography: Inter for UI; JetBrains Mono for callsigns, codes, SQL and numbers.

## Panels

- **Briefing:** latest `content_md` as Markdown, a "generated hh:mm UTC by <model>" line and a countdown to the next one.
- **Ask:** a text input (500-character limit shown) with 4 example-question chips. Each answer shows Markdown, a collapsible syntax-highlighted SQL block and a result table. 429 responses show "Limit reached, try again later".
- **Arrivals:** a segmented control VIE / BTS / BUD and a board with columns *callsign · from · ETA (p50) · range (p10–p90) · distance · phase*. Clicking a row selects the aircraft.
- **Events:** reverse-chronological feed with severity as colour **and** text label, UTC time and title; infinite scroll with the `/events` cursor. Clicking an event with a location flies the map there.
- **Aircraft card** (map overlay): callsign, type, registration, airline; altitude, speed and vertical rate in ft / kt / fpm; "Likely destination" with top-3 bars and the label "estimate"; ETA as p50 with the p10–p90 range, if one exists.
- **Anomaly legend:** "more / less traffic than usual for this hour of the week". Hovering a `low` cell adds "may be a receiver coverage gap". When `baseline_kind = cold_start`, a "baseline warming up" badge.

## Accessibility and performance

- All controls are real buttons and inputs with visible focus. Colour is never the only signal: severities and anomaly direction also have text.
- The Arrivals and Events panels are the list-view alternative to the map.
- **Budget:**
  - App shell (everything before the map) < 150 KB JS gzipped.
  - Map bundle (MapLibre + deck.gl, lazy-loaded) < 800 KB gzipped.
  - Live map visible in < 3 s on a 50 Mbit/s connection.
  - 60 fps with 12k icons on a laptop with integrated graphics.
