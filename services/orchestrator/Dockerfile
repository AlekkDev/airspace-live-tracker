# Build context: the repo root. One image for dagster-webserver, dagster-daemon and dagster-code.
FROM python:3.12-slim-bookworm AS build
RUN pip install --no-cache-dir uv==0.12.23
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock .python-version ./
# Every workspace member's pyproject.toml must exist for a frozen sync.
COPY collector/pyproject.toml collector/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/ingest/pyproject.toml services/ingest/pyproject.toml
COPY libs libs
COPY services/orchestrator services/orchestrator
RUN uv sync --frozen --no-dev --no-editable --package airspace-orchestrator

FROM python:3.12-slim-bookworm
# The backup job needs pg_dump matching the server (16, from the PGDG repository) and rclone.
RUN apt-get update  && apt-get install -y --no-install-recommends ca-certificates curl rclone  && install -d /usr/share/postgresql-common/pgdg  && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc       https://www.postgresql.org/media/keys/ACCC4CF8.asc  && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main"       > /etc/apt/sources.list.d/pgdg.list  && apt-get update  && apt-get install -y --no-install-recommends postgresql-client-16  && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10002 dagster
COPY --from=build /app/.venv /app/.venv
COPY services/orchestrator/dagster_home /opt/dagster/home
# Run logs and op outputs; a shared volume in compose, so the webserver can show them.
RUN install -d -o dagster -g dagster /opt/dagster/home/storage
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 DAGSTER_HOME=/opt/dagster/home
WORKDIR /opt/dagster/home
USER dagster
# The command is set per service in infra/compose.yml.
