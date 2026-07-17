"""Structured logging setup using structlog.

- Console renderer in development, JSON in production (``LOG_JSON=true``).
- A PII-masking processor scrubs emails / phone numbers from log values.
- ``request_id`` (and other bound context vars) are merged into every event.

Call ``configure_logging()`` once at startup, then use ``get_logger(__name__)``.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.config import settings
from app.utils.pii import mask_pii

# Structural log fields that must never be scrubbed (they contain digit runs
# like ISO timestamps that would otherwise be mistaken for PII).
_RESERVED_LOG_KEYS = frozenset(
    {"timestamp", "level", "logger", "logger_name", "request_id", "method"}
)


def _mask_pii_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask PII in string values of the event dict.

    Reserved structural keys (timestamp, level, ...) are left untouched so log
    metadata stays intact.
    """

    def _scrub(value: Any) -> Any:
        if isinstance(value, str):
            return mask_pii(value)
        if isinstance(value, dict):
            return {k: _scrub(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return type(value)(_scrub(v) for v in value)
        return value

    return {
        key: (val if key in _RESERVED_LOG_KEYS else _scrub(val)) for key, val in event_dict.items()
    }


def configure_logging() -> None:
    """Configure stdlib logging + structlog. Idempotent."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _mask_pii_processor,
    ]

    if settings.log_json:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger."""
    return structlog.get_logger(name)
