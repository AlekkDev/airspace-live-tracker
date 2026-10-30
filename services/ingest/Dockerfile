# Build context: the repo root.
FROM python:3.12-slim-bookworm AS build
RUN pip install --no-cache-dir uv==0.12.23
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock .python-version ./
COPY collector/pyproject.toml collector/pyproject.toml
COPY libs libs
COPY services/ingest services/ingest
RUN uv sync --frozen --no-dev --no-editable --package airspace-ingest

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 10001 ingest
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER ingest
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
# No access log: client IPs are never logged (docs/09-conventions.md#configuration-and-secrets).
CMD ["uvicorn", "--factory", "ingest.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
