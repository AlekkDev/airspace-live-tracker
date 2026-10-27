# 08 · Frontend

The interactive mockup (mock data, design reference) is linked in [10 Roadmap](10-roadmap.md#links).

## Stack

React 18 + TypeScript + Vite, MapLibre GL JS (basemap), deck.gl via `MapboxOverlay` (data layers), TanStack Query (REST), native `EventSource` (SSE), Tailwind CSS. Hosted on Cloudflare Pages.

Basemap: CARTO *Dark Matter* style to start (free for non-commercial use, with attribution). Self-hosted Protomaps PMTiles is a later option (open decision O3).

## Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ◆ Airspace Monitor   9,412 aircraft · snapshot 34 s ago · 2/2 collectors │
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
At widths under 900 px, the side panel moves below the map as a bottom sheet.

## Map layers (deck.gl)

| Layer | deck.gl class | Data | Notes |
|---|---|---|---|
| Aircraft | `IconLayer` | `/live/snapshot` + SSE | Plane glyph rotated by `track_deg`, coloured by altitude band, `pickable` |
| Selected trail | `PathLayer` | `/aircraft/{id}/track` | Altitude-coloured gradient per segment |
| Anomaly heatmap | `H3HexagonLayer` | `/anomalies` | Orange = more traffic than usual, blue = less; opacity ∝ \|z\| |
| Airports | `ScatterplotLayer` + `TextLayer` | `ref.airports` (static JSON) | Target airports highlighted |
| Event pulses | `ScatterplotLayer` (animated radius) | SSE `event` | 10 s pulse at the event location |

## Smooth motion between 90 s snapshots

Per aircraft we keep `{lon, lat, vel_ms, track_deg, t0}` from the last snapshot. On each animation frame:
- `Δt = min(now − t0, 120 s)`.
- Position is advanced along `track_deg` by `vel_ms · Δt` (flat-earth step, which is accurate enough at these distances).
- Aircraft on the ground and aircraft with `vel_ms < 30` are not extrapolated.
- When a new snapshot arrives, each aircraft eases from its extrapolated position to the reported one over 1.5 s, so nothing snaps.
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
| `--accent` | `#4cc3ff` | selection, links, focus |
| `--warn` | `#ffb547` | warnings, high-anomaly |
| `--alert` | `#ff6b6b` | emergency squawks |
| `--low` | `#5b8cff` | low-anomaly |

Altitude bands (aircraft colour):

| Band | Colour |
|---|---|
| on ground | `#7d8799` |
| < 3,000 m (≈ FL100) | `#ffb547` |
| 3,000–7,000 m | `#3ddc97` |
| 7,000–10,000 m | `#4cc3ff` |
| > 10,000 m | `#b392ff` |

Typography: Inter for UI; JetBrains Mono for callsigns, codes, SQL and numbers.

## Panels

- **Briefing:** latest `content_md` rendered as Markdown, with a "generated hh:mm by model" line and a countdown to the next one.
- **Ask:** an input with 4 example-question chips. Each answer shows Markdown, a collapsible SQL block (syntax-highlighted) and a small result table.
- **Arrivals:** a segmented control for VIE / BTS / BUD, and a board with columns *callsign · from · ETA (p50) · ±range · distance · phase*. Clicking a row selects the aircraft on the map.
- **Events:** a reverse-chronological feed with a severity colour, a time and a one-line title. Clicking flies the map to the location.
- **Aircraft card** (map overlay): callsign, type, registration, operator; altitude/speed/vertical rate in ft/kt/fpm; top-3 destination bars; ETA if one exists.

## Accessibility & performance

- All controls are real buttons/inputs with visible focus. Altitude colours also differ in lightness. The map has a "list view" fallback via the Arrivals/Events panels.
- Budget: first load < 300 KB JS gzipped (deck.gl modules imported à la carte); 60 fps with 12k icons on an integrated GPU.
