#!/bin/bash
# Runs once, when the data volume is first created. Creates what migrations cannot:
# login roles with passwords, the databases, and the extensions that need a superuser.
# Roles and privileges: docs/03-data-model.md#roles
set -euo pipefail

psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -v owner_pw="$AIRSPACE_OWNER_PASSWORD" \
  -v ingest_pw="$INGEST_WRITER_PASSWORD" \
  -v stream_pw="$STREAM_WORKER_PASSWORD" \
  -v jobs_pw="$JOBS_PASSWORD" \
  -v reader_pw="$APP_READER_PASSWORD" \
  -v llm_pw="$LLM_READONLY_PASSWORD" \
  -v grafana_pw="$GRAFANA_READER_PASSWORD" \
  -v dagster_pw="$DAGSTER_DB_PASSWORD" \
  -v mlflow_pw="$MLFLOW_DB_PASSWORD" <<'SQL'
CREATE ROLE airspace_owner LOGIN PASSWORD :'owner_pw';
CREATE ROLE ingest_writer  LOGIN PASSWORD :'ingest_pw';
CREATE ROLE stream_worker  LOGIN PASSWORD :'stream_pw';
CREATE ROLE jobs           LOGIN PASSWORD :'jobs_pw';
CREATE ROLE app_reader     LOGIN PASSWORD :'reader_pw';
CREATE ROLE llm_readonly   LOGIN PASSWORD :'llm_pw';
CREATE ROLE grafana_reader LOGIN PASSWORD :'grafana_pw';
CREATE ROLE dagster        LOGIN PASSWORD :'dagster_pw';
CREATE ROLE mlflow         LOGIN PASSWORD :'mlflow_pw';

ALTER ROLE llm_readonly SET default_transaction_read_only = on;
ALTER ROLE llm_readonly SET statement_timeout = '5s';
ALTER ROLE grafana_reader SET statement_timeout = '10s';

-- airspace_owner must be a member of jobs to hand it agg.traffic_h3_15m.
GRANT jobs TO airspace_owner;

CREATE DATABASE airspace OWNER airspace_owner;
CREATE DATABASE dagster OWNER dagster;
CREATE DATABASE mlflow OWNER mlflow;

\connect airspace
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;
SQL
