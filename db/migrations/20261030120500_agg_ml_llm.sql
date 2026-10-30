-- migrate:up
-- agg.traffic_h3_15m and agg.coverage_15m arrive with M1.10; the llm.v_* views arrive with the chat.

-- Robust baseline per cell and hour of week, recomputed daily
CREATE TABLE agg.baseline_h3_how (
  h3_r4 bigint, hour_of_week smallint,          -- 0..167, Monday 00:00 UTC = 0
  median_density real NOT NULL, mad_density real NOT NULL,
  n_weeks smallint NOT NULL,                    -- distinct weeks with data for this cell and hour
  computed_at timestamptz NOT NULL,
  PRIMARY KEY (h3_r4, hour_of_week)
);

CREATE TABLE ml.anomalies (                     -- only flagged cells are stored
  bucket timestamptz NOT NULL, h3_r4 bigint NOT NULL,
  observed real NOT NULL, expected real NOT NULL, robust_z real NOT NULL,
  direction text NOT NULL CHECK (direction IN ('high', 'low')),
  persistent boolean NOT NULL,                  -- also flagged, same direction, in the previous bucket
  baseline_kind text NOT NULL CHECK (baseline_kind IN ('hour_of_week', 'cold_start')),
  model_version text NOT NULL,
  PRIMARY KEY (bucket, h3_r4)
);
SELECT create_hypertable('ml.anomalies', 'bucket', chunk_time_interval => interval '7 days');
SELECT add_retention_policy('ml.anomalies', interval '90 days');

CREATE TABLE ml.eta_predictions (
  predicted_at timestamptz NOT NULL,            -- snapshot_time the prediction is based on
  flight_id uuid NOT NULL REFERENCES core.flights ON DELETE CASCADE,
  icao24 text NOT NULL, airport_icao text NOT NULL,
  eta_p10 timestamptz NOT NULL, eta_p50 timestamptz NOT NULL, eta_p90 timestamptz NOT NULL,
  distance_km real NOT NULL, model_version text NOT NULL,
  PRIMARY KEY (flight_id, predicted_at)
);
SELECT create_hypertable('ml.eta_predictions', 'predicted_at', chunk_time_interval => interval '1 day');
SELECT add_retention_policy('ml.eta_predictions', interval '30 days');

CREATE TABLE ml.dest_predictions (
  predicted_at timestamptz NOT NULL,
  flight_id uuid NOT NULL REFERENCES core.flights ON DELETE CASCADE,
  icao24 text NOT NULL,
  candidates jsonb NOT NULL,                    -- top 3: [{"icao":"LOWW","p":0.81}, ...]
  method text NOT NULL CHECK (method IN ('route_lookup', 'reranker')),
  model_version text NOT NULL,
  PRIMARY KEY (flight_id, predicted_at)
);
SELECT create_hypertable('ml.dest_predictions', 'predicted_at', chunk_time_interval => interval '1 day');
SELECT add_retention_policy('ml.dest_predictions', interval '14 days');

CREATE TABLE llm.briefings (
  briefing_id bigserial PRIMARY KEY, generated_at timestamptz NOT NULL,
  window_start timestamptz NOT NULL, window_end timestamptz NOT NULL UNIQUE,
  model text NOT NULL, prompt_version text NOT NULL, facts jsonb NOT NULL, content_md text NOT NULL,
  number_check text NOT NULL CHECK (number_check IN ('pass', 'fail')),
  input_tokens integer, output_tokens integer
);

CREATE TABLE llm.chat_log (                     -- no IP addresses or other user identifiers
  chat_id bigserial PRIMARY KEY, asked_at timestamptz NOT NULL,
  question text NOT NULL, sql text, row_count integer, answer_md text,
  latency_ms integer, error text, model text NOT NULL
);

-- migrate:down
