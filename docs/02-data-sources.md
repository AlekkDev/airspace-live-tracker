# 02 · Data sources

Facts below were checked against the providers' documentation on 2026-10-29. If a provider changes behaviour, update this file in the same PR as the code.

## OpenSky Network

**Server-side calls are not possible:** OpenSky blocks or throttles data-centre IP ranges, so every OpenSky request comes from the collector on a home connection ([ADR-0001](adr/0001-home-collectors-push-to-cloud.md)).

**Auth:** OAuth2 client credentials, handled by the collector.

**Attribution:** the map footer always shows *"Data: The OpenSky Network, opensky-network.org"*.

### Live state vectors

- `GET https://opensky-network.org/api/states/all?extended=1` (whole world; `extended=1` adds `category`).
- **Cadence:** one request every 90 s, 960 a day. This fits OpenSky's daily quota with a small margin for retries.
- **Headers:** `X-Rate-Limit-Remaining` (quota left) and, on HTTP 429, `X-Rate-Limit-Retry-After-Seconds`. Both go into the batch envelope.
- **Response:** `{ "time": <unix s>, "states": [[...], ...] }`. Each state is a positional array:

| # | Field | Type | Unit / note |
|---|---|---|---|
| 0 | icao24 | string | hex; lower-cased at ingest |
| 1 | callsign | string \| null | space-padded; trimmed at ingest |
| 2 | origin_country | string | country of registration, inferred from icao24 |
| 3 | time_position | int \| null | unix s of the last position update |
| 4 | last_contact | int | unix s of the last message of any kind |
| 5 | longitude | float \| null | WGS-84 degrees |
| 6 | latitude | float \| null | WGS-84 degrees |
| 7 | baro_altitude | float \| null | metres, pressure altitude (1013.25 hPa) |
| 8 | on_ground | bool | |
| 9 | velocity | float \| null | m/s over ground |
| 10 | true_track | float \| null | degrees clockwise from north |
| 11 | vertical_rate | float \| null | m/s, positive = climbing |
| 12 | sensors | int[] \| null | null (not requested) |
| 13 | geo_altitude | float \| null | metres, GNSS |
| 14 | squawk | string \| null | |
| 15 | spi | bool | special purpose indicator |
| 16 | position_source | int | 0 ADS-B, 1 ASTERIX, 2 MLAT, 3 FLARM |
| 17 | category | int | 0–20; e.g. 4 = Large, 6 = Heavy |

- **Known limits:**
  - Coverage is whatever OpenSky's volunteer receivers hear. Oceans and parts of Africa and Asia are sparse, and a receiver going offline lowers traffic in its area.
  - Positions can be stale (`time_position` well before `time`).
  - Positions and callsigns can be null.
  - Aircraft broadcast no origin or destination.

### OpenSky flight lists

- `GET https://opensky-network.org/api/flights/all?begin=<unix s>&end=<unix s>`, each window at most 2 hours.
- Data for a day is produced in a nightly batch, so the collector fetches **yesterday** at 06:00 UTC ([04](04-pipelines.md#p1--collector)).
- **Quota:** 12 requests a day, counted separately from the live map's quota.
- **Fields:** `icao24`, `callsign`, `firstSeen`, `lastSeen`, `estDepartureAirport`, `estArrivalAirport` (both nullable estimates), the horizontal and vertical distances to those airports, and candidate counts.
- **Use:** departure and arrival labels for `core.flights` (source `opensky`) and the route lookup `ref.callsign_routes`.

## Weather: METAR

- **Live:** `GET https://aviationweather.gov/api/data/metar?ids=LOWW,LZIB,LHBP&format=json&hours=3`, every 30 min.
- **Historical:** Iowa Environmental Mesonet ASOS archive (CSV by station and date range), loaded once by the manual `metar_backfill` job for the training period before live METAR started.
- **Parsed and stored in SI:** wind direction (deg), wind speed and gust (kt × 0.514444 → m/s), visibility (m), ceiling (ft × 0.3048 → m; lowest BKN/OVC/VV layer), temperature and dew point (°C), QNH (hPa), flight category, raw text.

## Historical routes: Zenodo

- OpenSky's COVID-19 flight dataset on Zenodo (2019–2022), monthly `flightlist_*.csv.gz`, DOI 10.5281/zenodo.3737101 (cited in the README), non-commercial licence (`LICENSE.txt` in the record).
- Converted once to Parquet and read with DuckDB.
- **Only use:** `routes_refresh` takes Zenodo rows for callsigns that have no OpenSky flight-list entry in the last 28 days. It is a fallback for the first weeks; routes change and the data includes the COVID years.

## Reference data

| Dataset | Source | Licence | Use | Refresh |
|---|---|---|---|---|
| Airports | OurAirports `airports.csv` | Public domain | ICAO/IATA, coordinates, type, elevation | seeded in M1, then monthly |
| Runways | OurAirports `runways.csv` | Public domain | Runway headings for wind components | seeded in M1, then monthly |
| Aircraft | OpenSky aircraft database CSV | Non-commercial, attribution | icao24 → registration, typecode, operator | monthly |
| Airlines | OpenFlights `airlines.dat` | ODbL 1.0 (attribution in README) | Callsign prefix → airline name | monthly |
| Countries | Natural Earth admin-0, 1:50m | Public domain | `over_country` for the chat; place names in briefings | monthly |
| H3 grid | `h3` Python library | Apache 2.0 | Cell ids, boundaries | n/a |

Airports and runways are loaded in M1 by the seed loader `db/seeds/ourairports.py` (downloads both CSVs, upserts on the primary key, safe to re-run), because go-around detection in M2 needs the target airports' elevations. From M3, `ref_refresh` keeps them current. The other datasets are first loaded by `ref_refresh` in M3.

## Target airports

| City | ICAO | IATA | Lat | Lon |
|---|---|---|---|---|
| Vienna | LOWW | VIE | 48.110 | 16.570 |
| Bratislava | LZIB | BTS | 48.170 | 17.213 |
| Budapest | LHBP | BUD | 47.437 | 19.256 |

Elevations come from `ref.airports`.
