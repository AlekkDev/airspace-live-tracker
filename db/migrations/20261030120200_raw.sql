-- migrate:up
CREATE TABLE raw.state_vectors (
  snapshot_time     timestamptz NOT NULL,       -- OpenSky response "time"
  icao24            text        NOT NULL,
  callsign          text,
  origin_country    text,                       -- country of registration, not position
  time_position     timestamptz,                -- last position update
  last_contact      timestamptz,
  lon               double precision,
  lat               double precision,
  baro_altitude_m   real,                       -- pressure altitude (1013.25 hPa reference)
  geo_altitude_m    real,                       -- GNSS altitude
  on_ground         boolean,
  velocity_ms       real,
  true_track_deg    real,
  vertical_rate_ms  real,
  squawk            text,
  spi               boolean,
  position_source   smallint,
  category          smallint,
  h3_r4             bigint,                     -- computed at ingest; NULL when lat/lon is NULL
  batch_id          uuid        NOT NULL,
  PRIMARY KEY (icao24, snapshot_time)
);

SELECT create_hypertable('raw.state_vectors', 'snapshot_time', chunk_time_interval => interval '1 day');
-- create_hypertable already creates the (snapshot_time DESC) index.
CREATE INDEX ON raw.state_vectors (h3_r4, snapshot_time DESC);

-- The compression policy is a separate migration, merged only after the M1 backlog drain.
ALTER TABLE raw.state_vectors SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'icao24',
  timescaledb.compress_orderby   = 'snapshot_time DESC'
);
SELECT add_retention_policy('raw.state_vectors', interval '90 days');

CREATE TABLE raw.opensky_flights (
  icao24          text        NOT NULL,
  first_seen      timestamptz NOT NULL,
  last_seen       timestamptz NOT NULL,
  callsign        text,
  est_dep_icao    text,                         -- NULL when OpenSky could not estimate it
  est_arr_icao    text,
  est_dep_horiz_m integer,
  est_arr_horiz_m integer,
  dep_candidates  smallint,
  arr_candidates  smallint,
  batch_id        uuid        NOT NULL,
  PRIMARY KEY (icao24, first_seen)
);
SELECT create_hypertable('raw.opensky_flights', 'first_seen', chunk_time_interval => interval '7 days');
SELECT add_retention_policy('raw.opensky_flights', interval '180 days');

-- migrate:down
