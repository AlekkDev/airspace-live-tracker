"""Structured JSON logging shared by every service (docs/09-conventions.md#code-conventions)."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog


def configure_logging(service: str, log_file: Path | None = None) -> None:
    """JSON lines to stdout and, if given, to a rotating file (10 MB x 5)."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5, encoding="utf-8")
        )
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=handlers, force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # it logs every request URL at INFO
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    structlog.contextvars.bind_contextvars(service=service)
