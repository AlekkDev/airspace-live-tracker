# 02 · Data sources

> Items marked **(verify)** come from documentation as we understood it at design time. Check them against the live docs before relying on them in code, and update this file.

## OpenSky Network: live state vectors

- **Endpoint:** `GET https://opensky-network.org/api/states/all`, optional bounding box `lamin, lomin, lamax, lomax`, optional `extended=1` (adds aircraft `category`).
- **Auth:** OAuth2 *client credentials*. Create an API client in your OpenSky account and exchange `client_id` + `client_secret` for a bearer token at the OpenSky auth server. Tokens are short-lived (~30 min) and must be refreshed **(verify)**. Basic auth is deprecated.
- **Response:** `{ "time": <unix s>, "states": [[...], ...] }`. Each state is a positional array:

| # | Field | Type | Unit / note |
|---|---|---|---|
| 0 | icao24 | string | hex, lower-case |
| 1 | callsign | string \| null | padded with spaces → trim |
| 2 | origin_country | string | inferred from icao24 |
| 3 | time_position | int \| null | unix s of last position update |
| 4 | last_contact | int | unix s of last message of any kind |
| 5 | longitude | float \| null | WGS-84 degrees |
| 6 | latitude | float \| null | WGS-84 degrees |
| 7 | baro_altitude | float \| null | metres |
| 8 | on_ground | bool | |
| 9 | velocity | float \| null | m/s over ground |
| 10 | true_track | float \| null | degrees clockwise from north |
| 11 | vertical_rate | float \| null | m/s, + climbing |
| 12 | sensors | int[] \| null | receiver ids (null unless requested) |
| 13 | geo_altitude | float \| null | metres |
| 14 | squawk | string \| null | |
| 15 | spi | bool | special purpose indicator |
| 16 | position_source | int | 0 ADS-B, 1 ASTERIX, 2 MLAT, 3 FLARM |
| 17 | category | int | only with `extended=1` |

- **Credits (verify):** each request costs credits by area. Bounding boxes up to ~25 sq deg cost 1, then 2, 3, and **4 for > 400 sq deg or global**. Daily budget: ~4,000 for a registered user, ~8,000 for an active feeder. 4,000 / 4 = 1,000 global calls/day, which is one call every **86.4 s**. That is where the 90 s cadence comes from.
- **Headers:** `X-Rate-Limit-Remaining` (credits left) and, on HTTP 429, `X-Rate-Limit-Retry-After-Seconds` **(verify)**. The collector logs both into `ops.ingest_batches`.
- **Licence:** free for research and non-commercial use; attribution required. The map footer shows *"Data: The OpenSky Network, opensky-network.org"*.
- **Known quirks:** positions can be stale (`time_position` ≪ `time`), so the collector keeps both. Null positions happen. Callsigns can be empty. Coverage over oceans and parts of Africa/Asia is sparse.

### Query plan (config, not code)

The collector reads a list of query slots from config. Default:

```yaml
cadence_seconds: 90
offset_seconds: 0        # collector B uses 45
queries:
  - kind: global
    extended: true
```

Alternative to evaluate in M1 (open decision O4): global every 180 s + Central Europe box (lat 44–52, lon 9–24, ~120 sq deg = 3 credits **(verify)**) every 60 s. This trades world freshness for better ETA data around our three airports.

## Zenodo: OpenSky COVID-19 flight dataset

- **What:** monthly `flightlist_YYYYMMDD_YYYYMMDD.csv.gz` files, one row per flight. Coverage is 2019 through 2022 **(verify the latest version on Zenodo)**.
- **Columns:** `callsign, number, icao24, registration, typecode, origin, destination, firstseen, lastseen, day, latitude_1, longitude_1, altitude_1, latitude_2, longitude_2, altitude_2`.
- **Use:**
  - Route priors: callsign → destination distribution for destination prediction.
  - Aircraft type mix.
  - Historical weekly traffic patterns, to sanity-check our own baselines.
- **Not useful for:** ETA. There are no trajectories, only first/last seen.
- **Storage:** converted once to Parquet (partitioned by month) and queried with DuckDB in training jobs. Only the derived `ref.callsign_routes` table goes into Postgres. ~4 years × ~2.5M flights/month is too much to keep in the live database for no benefit.
- **Licence:** CC BY 4.0; cite the dataset DOI in the README.

## Weather: METAR

- **Live:** aviationweather.gov Data API, e.g. `GET https://aviationweather.gov/api/data/metar?ids=LOWW,LZIB,LHBP&format=json` **(verify parameters)**. Polled every 30 min for the three target airports plus the ~50 busiest European airports.
- **Historical:** Iowa Environmental Mesonet ASOS/METAR archive (CSV download by station and date range). Used to backfill weather features for training windows.
- **Parsed fields:** wind direction/speed/gust, visibility, ceiling, temperature, dew point, QNH, flight category (VFR/MVFR/IFR/LIFR), and the raw text.

## Reference data

| Dataset | Source | Use | Refresh |
|---|---|---|---|
| Airports | OurAirports `airports.csv` (public domain) | ICAO/IATA codes, coordinates, type, elevation | monthly |
| Runways | OurAirports `runways.csv` | runway headings, for head/crosswind features | monthly |
| Aircraft database | OpenSky aircraft database CSV | icao24 → registration, typecode, operator | monthly |
| H3 grid | `h3` Python library (computed) | cell ids, boundaries | n/a |

## Target airports

| City | ICAO | IATA | Lat | Lon |
|---|---|---|---|---|
| Vienna | LOWW | VIE | 48.110 | 16.570 |
| Bratislava | LZIB | BTS | 48.170 | 17.213 |
| Budapest | LHBP | BUD | 47.437 | 19.256 |
