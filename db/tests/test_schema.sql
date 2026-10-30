-- Runs against a throwaway database (infra/test-db.sh) as the postgres superuser. Any failure stops psql.
\set ON_ERROR_STOP on

CREATE FUNCTION public.assert_denied(stmt text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE stmt;
  EXCEPTION WHEN insufficient_privilege THEN
    RETURN;
  END;
  RAISE EXCEPTION 'expected permission denied: %', stmt;
END $$;

-- The image must ship a TimescaleDB without the #7672 bug
DO $$
BEGIN
  IF string_to_array(split_part(extversion, '-', 1), '.')::int[] < ARRAY[2, 19]
     FROM pg_extension WHERE extname = 'timescaledb' THEN
    RAISE EXCEPTION 'TimescaleDB older than 2.19';
  END IF;
END $$;

INSERT INTO ops.collectors (collector_id, owner, offset_seconds, api_key_hash) VALUES ('test-01', 'test', 0, 'x');

-- ingest_writer: stores a batch; re-uploading it changes nothing
SET ROLE ingest_writer;
INSERT INTO ops.ingest_batches (batch_id, collector_id, query_kind, requested_at, snapshot_time, http_status)
VALUES ('00000000-0000-7000-8000-000000000001', 'test-01', 'states_global', '2026-10-30 12:00Z', '2026-10-30 12:00Z', 200);
INSERT INTO raw.state_vectors (snapshot_time, icao24, batch_id) VALUES
  ('2026-10-30 12:00Z', 'aaaaaa', '00000000-0000-7000-8000-000000000001'),
  ('2026-10-30 12:00Z', 'bbbbbb', '00000000-0000-7000-8000-000000000001');
INSERT INTO raw.state_vectors (snapshot_time, icao24, batch_id) VALUES
  ('2026-10-30 12:00Z', 'aaaaaa', '00000000-0000-7000-8000-000000000001')
ON CONFLICT DO NOTHING;
SELECT public.assert_denied('SELECT * FROM core.flights');
SELECT public.assert_denied('DELETE FROM raw.state_vectors');
RESET ROLE;

DO $$
BEGIN
  IF (SELECT count(*) FROM raw.state_vectors) <> 2 THEN
    RAISE EXCEPTION 're-upload changed the row count';
  END IF;
END $$;

-- #7672: inserting into a compressed chunk keeps every non-duplicate row
SELECT compress_chunk(c) FROM show_chunks('raw.state_vectors') c;
SET ROLE ingest_writer;
INSERT INTO raw.state_vectors (snapshot_time, icao24, batch_id) VALUES
  ('2026-10-30 12:00Z', 'aaaaaa', '00000000-0000-7000-8000-000000000001'),
  ('2026-10-30 12:00Z', 'cccccc', '00000000-0000-7000-8000-000000000001'),
  ('2026-10-30 12:01Z', 'aaaaaa', '00000000-0000-7000-8000-000000000001')
ON CONFLICT DO NOTHING;
RESET ROLE;
DO $$
BEGIN
  IF (SELECT count(*) FROM raw.state_vectors) <> 4 THEN
    RAISE EXCEPTION 'compressed-chunk insert lost or duplicated rows';
  END IF;
END $$;

-- Generated column and event trigger work
DO $$
BEGIN
  IF (SELECT late_seconds FROM ops.ingest_batches) IS NULL THEN
    RAISE EXCEPTION 'late_seconds not generated';
  END IF;
END $$;

-- stream_worker: writes events, cannot write raw data
SET ROLE stream_worker;
INSERT INTO core.events (dedupe_key, ts, kind, severity, title) VALUES ('dq_fail:x:1', now(), 'dq_fail', 'warn', 't');
SELECT public.assert_denied($q$INSERT INTO raw.state_vectors (snapshot_time, icao24, batch_id) VALUES (now(), 'x', gen_random_uuid())$q$);
RESET ROLE;

-- jobs: writes core and ml, reads raw
SET ROLE jobs;
INSERT INTO ops.job_runs (job, window_start, window_end, started_at, status) VALUES ('t', now(), now(), now(), 'ok');
SELECT count(*) FROM raw.state_vectors;
SELECT public.assert_denied('DELETE FROM raw.state_vectors');
RESET ROLE;

-- app_reader: reads data and collector views, never key hashes
SET ROLE app_reader;
SELECT count(*) FROM raw.state_vectors;
SELECT count(*) FROM ops.v_collectors;
INSERT INTO llm.chat_log (asked_at, question, model) VALUES (now(), 'q', 'm');
SELECT public.assert_denied('SELECT * FROM ops.collectors');
SELECT public.assert_denied('INSERT INTO core.flights (flight_id, icao24, first_seen, last_seen, status, n_points) VALUES (gen_random_uuid(), $$x$$, now(), now(), $$active$$, 0)');
RESET ROLE;

-- llm_readonly: nothing but llm.v_*
SET ROLE llm_readonly;
SELECT public.assert_denied('SELECT * FROM raw.state_vectors');
SELECT public.assert_denied('SELECT * FROM llm.chat_log');
SELECT public.assert_denied('SELECT * FROM ops.v_collectors');
RESET ROLE;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole
                 WHERE r.rolname = 'llm_readonly' AND 'default_transaction_read_only=on' = ANY (s.setconfig)) THEN
    RAISE EXCEPTION 'llm_readonly is not read-only by default';
  END IF;
END $$;

-- grafana_reader: never key hashes
SET ROLE grafana_reader;
SELECT count(*) FROM ops.v_collectors;
SELECT public.assert_denied('SELECT * FROM ops.collectors');
SELECT public.assert_denied('SELECT * FROM raw.state_vectors');
RESET ROLE;

\echo all schema tests passed
