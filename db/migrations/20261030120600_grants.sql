-- migrate:up
-- Privileges from docs/03-data-model.md#roles. Default privileges keep whole-schema grants true for later tables.

-- ingest_writer
GRANT USAGE ON SCHEMA ops, raw TO ingest_writer;
GRANT SELECT ON ops.collectors, ops.ingest_batches TO ingest_writer;
GRANT INSERT ON raw.state_vectors, raw.opensky_flights, ops.ingest_batches TO ingest_writer;

-- stream_worker
GRANT USAGE ON SCHEMA raw, ref, core, ml, ops TO stream_worker;
GRANT SELECT ON ALL TABLES IN SCHEMA raw, ref, core, ml TO stream_worker;
GRANT INSERT ON core.events, ml.eta_predictions TO stream_worker;
GRANT USAGE ON SEQUENCE core.events_event_id_seq TO stream_worker;
GRANT SELECT, UPDATE ON ops.stream_state TO stream_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, ref, core, ml GRANT SELECT ON TABLES TO stream_worker;

-- jobs
GRANT USAGE ON SCHEMA raw, ref, core, agg, ml, llm, ops TO jobs;
GRANT CREATE ON SCHEMA agg TO jobs;   -- owns agg.traffic_h3_15m (M1.10)
GRANT SELECT ON ALL TABLES IN SCHEMA raw, ref, core, agg, ml, llm, ops TO jobs;
GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ref, core, ml TO jobs;
GRANT INSERT, UPDATE, DELETE ON agg.baseline_h3_how, llm.briefings, ops.job_runs, ops.dq_results, ops.model_runs TO jobs;
GRANT USAGE ON SEQUENCE core.events_event_id_seq, llm.briefings_briefing_id_seq, ops.job_runs_run_id_seq TO jobs;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, agg, llm, ops GRANT SELECT ON TABLES TO jobs;
ALTER DEFAULT PRIVILEGES IN SCHEMA ref, core, ml GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO jobs;

-- app_reader
GRANT USAGE ON SCHEMA raw, ref, core, agg, ml, llm, ops TO app_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA raw, ref, core, agg, ml, llm TO app_reader;
GRANT SELECT ON ops.v_collectors, ops.v_ingest_batches, ops.dq_results TO app_reader;
GRANT INSERT ON llm.chat_log TO app_reader;
GRANT USAGE ON SEQUENCE llm.chat_log_chat_id_seq TO app_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, ref, core, agg, ml, llm GRANT SELECT ON TABLES TO app_reader;

-- llm_readonly: only llm.v_*, granted view by view when the views are created
GRANT USAGE ON SCHEMA llm TO llm_readonly;

-- grafana_reader
GRANT USAGE ON SCHEMA ops, agg, core TO grafana_reader;
GRANT SELECT ON ops.v_collectors, ops.v_ingest_batches, ops.job_runs, ops.dq_results, ops.model_runs, core.events TO grafana_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA agg TO grafana_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA agg GRANT SELECT ON TABLES TO grafana_reader;

-- migrate:down
