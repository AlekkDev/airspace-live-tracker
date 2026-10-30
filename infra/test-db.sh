#!/bin/bash
# Applies all migrations to a throwaway database and runs db/tests. Never touches the real data volume.
set -euo pipefail
cd "$(dirname "$0")"

env_file=$(mktemp)
for var in POSTGRES AIRSPACE_OWNER INGEST_WRITER STREAM_WORKER JOBS APP_READER LLM_READONLY GRAFANA_READER DAGSTER_DB MLFLOW_DB; do
  echo "${var}_PASSWORD=test" >> "$env_file"
done
dc() { docker compose -p airspace-test --env-file "$env_file" -f compose.yml "$@"; }
cleanup() { dc --profile tools down -v --remove-orphans >/dev/null 2>&1; rm -f "$env_file"; }
trap cleanup EXIT

dc up -d --wait db
dc run --rm migrate
# Applying again must be a no-op.
dc run --rm migrate
dc exec -T db psql -U postgres -d airspace -q -f - < ../db/tests/test_schema.sql
