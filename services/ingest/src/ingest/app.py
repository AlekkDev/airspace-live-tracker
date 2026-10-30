"""`POST /ingest/v1/batches` (docs/05-api-contract.md#post-ingestv1batches)."""

import gzip
import json
import zlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from airspace_common.log import configure_logging
from airspace_common.settings import IngestSettings
from ingest.normalize import Envelope, InvalidBatch, normalize
from ingest.store import DuplicateBatch, PgStore, Store

MAX_BODY_BYTES = 20_000_000

log = structlog.get_logger()
hasher = PasswordHasher()


class _TooLarge(Exception):
    pass


def _decompress(body: bytes) -> bytes:
    inflater = zlib.decompressobj(wbits=zlib.MAX_WBITS | 16)
    data = inflater.decompress(body, MAX_BODY_BYTES + 1)
    if len(data) > MAX_BODY_BYTES:
        raise _TooLarge
    if not inflater.eof:
        raise gzip.BadGzipFile("truncated gzip body")
    return data


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"status": "error", "detail": detail}, status_code=status)


def _authorized(store: Store, collector_id: Any, authorization: str | None) -> bool:
    scheme, _, key = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not key or not isinstance(collector_id, str):
        return False
    collector = store.collector(collector_id)
    if collector is None or collector.disabled:
        return False
    try:
        return hasher.verify(collector.api_key_hash, key)
    except (VerificationError, InvalidHashError):
        return False


def handle_batch(store: Store, body: bytes, encoding: str | None, auth: str | None) -> JSONResponse:
    try:
        data = _decompress(body) if encoding == "gzip" else body
        parsed = json.loads(data)
    except _TooLarge:
        return _error(413, "body over 20 MB")
    except (zlib.error, OSError, ValueError):
        return _error(422, "body is not valid JSON")
    collector_id = parsed.get("collector_id") if isinstance(parsed, dict) else None
    if not _authorized(store, collector_id, auth):
        return _error(401, "invalid collector key")

    batch_id = parsed.get("batch_id")
    try:
        envelope = Envelope.model_validate(parsed)
    except ValidationError as exc:
        log.warning("batch_invalid", batch_id=batch_id, errors=exc.error_count())
        return _error(422, "invalid envelope")
    if store.batch_exists(envelope.batch_id):
        return JSONResponse({"status": "duplicate"}, status_code=200)
    try:
        normalized = normalize(envelope)
    except InvalidBatch as exc:
        log.warning("batch_invalid", batch_id=batch_id, error=str(exc))
        return _error(422, str(exc))
    try:
        n_inserted = store.save(envelope, normalized)
    except DuplicateBatch:
        return JSONResponse({"status": "duplicate"}, status_code=200)
    log.info(
        "batch_stored",
        batch_id=batch_id,
        collector_id=envelope.collector_id,
        kind=envelope.query.kind,
        n_states=normalized.n_states,
        n_inserted=n_inserted,
        n_rejected=normalized.n_rejected,
    )
    return JSONResponse(
        {
            "status": "accepted",
            "n_states": normalized.n_states,
            "n_inserted": n_inserted,
            "n_rejected": normalized.n_rejected,
        },
        status_code=202,
    )


def build_app(store: Store) -> FastAPI:
    app = FastAPI(title="airspace ingest-api", docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/ingest/v1/batches")
    async def post_batch(request: Request) -> JSONResponse:
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_BODY_BYTES:
                return _error(413, "body over 20 MB")
        return await run_in_threadpool(
            handle_batch,
            store,
            bytes(body),
            request.headers.get("content-encoding"),
            request.headers.get("authorization"),
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        await run_in_threadpool(store.ping)
        return {"status": "ok"}

    return app


def create_app() -> FastAPI:
    """Entry point for uvicorn."""
    settings = IngestSettings()
    configure_logging("ingest")
    store = PgStore(settings.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        store.pool.open()
        yield
        store.pool.close()

    app = build_app(store)
    app.router.lifespan_context = lifespan
    return app
