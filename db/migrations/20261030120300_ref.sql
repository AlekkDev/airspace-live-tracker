-- migrate:up
CREATE TABLE ref.airports (
  icao text PRIMARY KEY, iata text, name text NOT NULL, type text NOT NULL,  -- OurAirports type
  lat double precision NOT NULL, lon double precision NOT NULL, elevation_m real NOT NULL,
  country text, is_target boolean NOT NULL DEFAULT false,                  -- true for LOWW, LZIB, LHBP
  geom geography(Point, 4326) NOT NULL
);
CREATE INDEX ON ref.airports USING gist (geom);

CREATE TABLE ref.runways (
  airport_icao text REFERENCES ref.airports, le_ident text, he_ident text,
  le_heading_deg real, he_heading_deg real, length_m real,
  PRIMARY KEY (airport_icao, le_ident)
);

CREATE TABLE ref.aircraft (
  icao24 text PRIMARY KEY, registration text, typecode text,
  manufacturer text, model text, operator text, operator_icao text
);

CREATE TABLE ref.airlines (                     -- OpenFlights airlines.dat, active airlines with an ICAO code
  icao text PRIMARY KEY, name text NOT NULL, country text
);

CREATE TABLE ref.countries (                    -- Natural Earth admin-0, 1:50m
  iso_a2 text PRIMARY KEY, name text NOT NULL, geom geography(MultiPolygon, 4326) NOT NULL
);

CREATE TABLE ref.h3_r4_country (                -- country containing each H3 r4 cell centre; computed once
  h3_r4 bigint PRIMARY KEY, iso_a2 text REFERENCES ref.countries
);

CREATE TABLE ref.callsign_routes (              -- route lookup: P(destination | callsign)
  callsign    text NOT NULL,
  destination text NOT NULL,                    -- ICAO; rows without a destination are never stored
  n_flights   integer NOT NULL,
  share       real NOT NULL,                    -- n_flights / all flights of this callsign in the window
  last_seen   date NOT NULL,
  source      text NOT NULL CHECK (source IN ('opensky', 'zenodo')),
  PRIMARY KEY (callsign, destination)
);

-- migrate:down
