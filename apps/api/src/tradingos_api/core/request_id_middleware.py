"""Per-request correlation ID + structured access logging (Revision
Prompt 16). Pure request/response bookkeeping — no DB access — so
`BaseHTTPMiddleware` is fine here for the same reason it's fine in
`core/security_headers.py` (unlike `core/dependencies.py::require_session()`,
which specifically needs to be a FastAPI dependency for
`dependency_overrides`/test-transaction reasons).
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from tradingos_api.core.logging import (
    get_request_id,
    new_request_id,
    reset_request_id,
    set_request_id,
)
from tradingos_api.core.metrics import request_metrics

_REQUEST_ID_HEADER = "X-Request-ID"
_access_logger = logging.getLogger("tradingos_api.access")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = new_request_id()
        token = set_request_id(request_id)
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            # The global exception handler (main.py) logs the failure
            # itself with full context — this branch exists only so
            # the access line below still fires (and the request ID is
            # still reset) on an unhandled exception, not to duplicate
            # that logging.
            duration_ms = round((time.monotonic() - started) * 1000, 2)
            request_metrics.record(status_code=500, duration_ms=duration_ms)
            _access_logger.info(
                "request failed",
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "user_id": getattr(request.state, "user_id", None),
                },
            )
            raise
        finally:
            reset_request_id(token)

        duration_ms = round((time.monotonic() - started) * 1000, 2)
        request_metrics.record(status_code=response.status_code, duration_ms=duration_ms)
        response.headers[_REQUEST_ID_HEADER] = request_id
        _access_logger.info(
            "request handled",
            extra={
                "http_method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "user_id": getattr(request.state, "user_id", None),
            },
        )
        return response


__all__ = ["RequestIdMiddleware", "get_request_id"]
