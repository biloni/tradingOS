"""Structured JSON logging + redaction + request correlation (Revision
Prompt 16). Stdlib-only (`logging` + `contextvars`), matching this
project's existing "no new dependency for a single-user app" pattern
(`core/auth.py` did the same thing for password hashing) — a full
`structlog`/`loguru` stack would be solving a multi-service-fleet
observability problem this app doesn't have.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from tradingos_api.core.config import get_settings

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)

# Extra-field keys whose *values* are always redacted regardless of
# what they contain — defense in depth for a secret this process
# doesn't already know the literal value of (e.g. a session/CSRF token
# a future call site might carelessly pass via `extra=`). The known-
# value scrub below (`_known_secret_values()`) is the primary defense;
# this is the fallback for values that scrub can't anticipate.
_SENSITIVE_EXTRA_KEYS = frozenset(
    {"password", "raw_token", "session_token", "csrf_token", "token", "api_key", "secret"}
)
_REDACTED = "[REDACTED]"


def get_request_id() -> str | None:
    return _REQUEST_ID.get()


def set_request_id(request_id: str | None) -> Any:
    """Returns the `contextvars.Token` for `reset()` — mirrors
    `ContextVar.set()`'s own return contract so callers can restore the
    previous value in a `finally` block."""
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Any) -> None:
    _REQUEST_ID.reset(token)


def _known_secret_values() -> list[str]:
    """The literal secret strings this process currently holds —
    Anthropic/Alpaca keys plus the DB password parsed out of
    `database_url`. Scrubbing by *known value* catches a secret leaking
    into a log line by any path (an f-string, a repr'd exception, an
    object dump) — not just ones logged through a suspiciously-named
    field, which is all field-name-based redaction alone could catch."""
    settings = get_settings()
    values = [
        settings.anthropic_api_key,
        settings.alpaca_api_key_id,
        settings.alpaca_api_secret_key,
    ]
    parsed = urlsplit(settings.database_url)
    if parsed.password:
        values.append(parsed.password)
    return [v for v in values if v]


class RedactingFilter(logging.Filter):
    """Applied to every handler (see `configure_logging()`), not just
    some — a filter attached to a handler runs for every record that
    reaches it, so this is the one place a secret cannot get through
    regardless of which logger or call site produced the record."""

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = _known_secret_values()
        message = record.getMessage()
        record.msg = _scrub_known_values(message, secrets)
        record.args = ()  # message is already fully formatted above

        for key in list(record.__dict__.keys()):
            if key.lower() in _SENSITIVE_EXTRA_KEYS:
                record.__dict__[key] = _REDACTED
            elif isinstance(record.__dict__.get(key), str):
                record.__dict__[key] = _scrub_known_values(record.__dict__[key], secrets)
        return True


def _scrub_known_values(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, _REDACTED)
    return text


# Standard `LogRecord` attributes — anything else set via `extra={...}`
# is a caller-supplied structured field and gets included in the JSON
# output verbatim (after redaction, above).
_STANDARD_RECORD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_KEYS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Idempotent — safe to call more than once (tests/`--reload` both
    re-import `main`). Replaces any handlers already attached to the
    root logger rather than accumulating duplicates."""
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)

    # uvicorn's own loggers otherwise use their own plain-text
    # formatter, bypassing both the JSON shape and the redaction
    # filter above — routing them through the root logger's handler
    # keeps every line in this process the same shape.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True


def new_request_id() -> str:
    return uuid.uuid4().hex


__all__ = [
    "JsonFormatter",
    "RedactingFilter",
    "configure_logging",
    "get_request_id",
    "new_request_id",
    "reset_request_id",
    "set_request_id",
]
