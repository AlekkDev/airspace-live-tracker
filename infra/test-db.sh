#!/bin/bash
# Applies all migrations to a throwaway database and runs db/tests. Never touches the real data volume.
set -euo pipefail
cd "$(dirname "$0")"

env_file=$(mktemp)
for var in POSTGRES AIRSPACE_OWNER INGEST_WRITER STREAM_WORKER JOBS APP_READER LLM_READONLY GRAFANA_READER DAGSTER_DB MLFLOW_DB BACKUP; do
  echo "${var}_PASSWORD=test" >> "$env_file"
done
echo "INGEST_HOST_PORT=18000" >> "$env_file"  # the real ingest-api may be using 8000
echo "DAGSTER_HOST_PORT=13000" >> "$env_file"
# The backup job writes to a local directory instead of R2.
{ echo "R2_RCLONE_TYPE=local"; echo "BACKUP_BUCKET=/tmp/r2/airspace-backup"; echo "ARCHIVE_BUCKET=/tmp/r2/airspace-archive"; } >> "$env_file"
dc() { docker compose -p airspace-test --env-file "$env_file" -f compose.yml "$@"; }
cleanup() { dc --profile tools down -v --remove-orphans >/dev/null 2>&1; rm -f "$env_file"; }
trap cleanup EXIT

dc up -d --wait db
dc run --rm migrate
# Applying again must be a no-op.
dc run --rm migrate
dc exec -T db psql -U postgres -d airspace -q -f - < ../db/tests/test_schema.sql

dc build ingest-api
dc up -d --wait ingest-api
key=$(dc run --rm -T ingest-admin add-collector --id smoke-01 --owner test --offset 0)
dc exec -T -e COLLECTOR_KEY="$key" ingest-api python - < ../db/tests/ingest_smoke.py

# Dagster: the webserver loads the `airspace` code location from dagster-code.
dc build dagster-code
dc up -d --wait dagster-code dagster-webserver dagster-daemon
dc exec -T dagster-webserver python - < ../services/orchestrator/tests/smoke_webserver.py

# Backup and restore drill: dump without raw chunk data, restore into a new database, compare.
dc exec -T dagster-code dagster job execute -m orchestrator.definitions -j backup
dc exec -T dagster-code sh -c 'cat /tmp/r2/airspace-backup/*/airspace.dump'   | dc exec -T db sh -c 'cat > /tmp/airspace.dump'
dc exec -T db sh -c 'psql -U postgres -q -v ON_ERROR_STOP=1 -c "CREATE DATABASE restore_drill"   && psql -U postgres -d restore_drill -q -v ON_ERROR_STOP=1        -c "CREATE EXTENSION IF NOT EXISTS timescaledb" -c "SELECT timescaledb_pre_restore()" >/dev/null   && pg_restore -U postgres -d restore_drill --no-owner /tmp/airspace.dump   && psql -U postgres -d restore_drill -q -c "SELECT timescaledb_post_restore()" >/dev/null'
dc exec -T db psql -U postgres -d restore_drill -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
  IF (SELECT count(*) FROM raw.state_vectors) <> 0 THEN
    RAISE EXCEPTION 'raw chunk data was not excluded from the backup';
  END IF;
  IF (SELECT count(*) FROM ops.collectors) < 2 OR (SELECT count(*) FROM ops.ingest_batches) = 0 THEN
    RAISE EXCEPTION 'restored backup lost ops data';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM timescaledb_information.hypertables
                 WHERE hypertable_schema = 'raw' AND hypertable_name = 'state_vectors') THEN
    RAISE EXCEPTION 'raw.state_vectors is not a hypertable after restore';
  END IF;
END $$;
SQL
echo "backup and restore drill passed"
