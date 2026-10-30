-- migrate:up
CREATE TABLE core.flights (
  flight_id        uuid PRIMARY KEY,            -- UUIDv7, assigned once when the flight opens; never changes
  icao24           text NOT NULL,
  callsign         text,                        -- latest non-NULL callsign
  first_seen       timestamptz NOT NULL,
  last_seen        timestamptz NOT NULL,
  dep_icao         text,
  dep_source       text CHECK (dep_source IN ('observed', 'opensky')),
  arr_icao         text,
  arr_source       text CHECK (arr_source IN ('observed', 'opensky')),
  arrived_at       timestamptz,                 -- observed touchdown at a target airport; the ETA label
  arrival_method   text CHECK (arrival_method IN ('on_ground', 'last_airborne')),
  height_method    text CHECK (height_method IN ('qnh', 'uncorrected', 'geo')),
  status           text NOT NULL CHECK (status IN ('active', 'completed', 'lost')),
  finalized        boolean NOT NULL DEFAULT false,
  max_alt_m        real,
  n_points         integer NOT NULL,
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ON core.flights (icao24) WHERE status = 'active';   -- at most one open flight per aircraft
CREATE INDEX ON core.flights (icao24, last_seen DESC);
CREATE INDEX ON core.flights (arr_icao, arrived_at);

CREATE TABLE core.metar (
  station text, observed_at timestamptz, raw_text text NOT NULL,
  wind_dir_deg smallint, wind_speed_ms real, gust_ms real,     -- wind_dir_deg NULL when variable
  visibility_m integer, ceiling_m integer,                     -- ceiling NULL when none reported
  temp_c real, dewpoint_c real, qnh_hpa real,
  flight_category text CHECK (flight_category IN ('VFR', 'MVFR', 'IFR', 'LIFR')),
  PRIMARY KEY (station, observed_at)
);

CREATE TABLE core.events (
  event_id     bigserial PRIMARY KEY,
  dedupe_key   text NOT NULL UNIQUE,            -- see docs/03-data-model.md
  ts           timestamptz NOT NULL,            -- when it happened (data time)
  created_at   timestamptz NOT NULL DEFAULT now(),
  kind         text NOT NULL CHECK (kind IN ('squawk_7500', 'squawk_7600', 'squawk_7700', 'go_around',
                 'holding', 'anomaly_start', 'anomaly_end', 'collector_gap', 'dq_fail')),
  severity     text NOT NULL CHECK (severity IN ('info', 'warn', 'alert')),
  lon          double precision,                -- NULL only for collector_gap and dq_fail
  lat          double precision,
  icao24       text, callsign text,
  flight_id    uuid REFERENCES core.flights ON DELETE SET NULL,
  airport_icao text, h3_r4 bigint,
  title        text NOT NULL,                   -- one line, shown in the feed
  payload      jsonb
);
CREATE INDEX ON core.events (ts DESC, event_id DESC);

-- Push recent events to the live stream; backfilled events are not pushed
CREATE FUNCTION core.notify_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.ts >= now() - interval '10 minutes' THEN
    PERFORM pg_notify('new_event', NEW.event_id::text);
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER events_notify AFTER INSERT ON core.events FOR EACH ROW EXECUTE FUNCTION core.notify_event();

-- migrate:down
