# Build context: the repo root. Built for linux/amd64 and linux/arm64 (the Raspberry Pi).
FROM python:3.12-slim-bookworm AS build
RUN pip install --no-cache-dir uv==0.12.23
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock .python-version ./
# Every workspace member's pyproject.toml must exist for a frozen sync.
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/ingest/pyproject.toml services/ingest/pyproject.toml
COPY services/orchestrator/pyproject.toml services/orchestrator/pyproject.toml
COPY libs libs
COPY collector collector
RUN uv sync --frozen --no-dev --no-editable --package airspace-collector

FROM python:3.12-slim-bookworm
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 SPOOL_DIR=/data/spool
WORKDIR /data
# The user is set by compose, so spool files belong to the host user that owns the bind mount.
CMD ["python", "-m", "collector"]
