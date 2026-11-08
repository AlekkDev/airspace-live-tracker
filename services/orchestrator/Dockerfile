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
RUN useradd --create-home --uid 10002 dagster
COPY --from=build /app/.venv /app/.venv
COPY services/orchestrator/dagster_home /opt/dagster/home
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 DAGSTER_HOME=/opt/dagster/home
WORKDIR /opt/dagster/home
USER dagster
# The command is set per service in infra/compose.yml.
