"""Security response headers (Revision Prompt 16). Pure response
post-processing — never touches the DB or a session — so plain
`BaseHTTPMiddleware` is fine here (unlike auth, which needed to be a
FastAPI dependency for `dependency_overrides`/test-transaction reasons;
see `core/dependencies.py::require_session()`'s docstring).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from tradingos_api.core.config import get_settings

# FastAPI's own auto-registered docs UI needs inline styles/scripts from
# a CDN — a strict API-wide CSP would break Swagger UI. `main.py`
# already documents `/docs`/`/redoc`/`/openapi.json` as a deliberate,
# scoped exception to the auth gate for the same reason (not intended
# for public exposure); this list mirrors that same carve-out for CSP
# only, not for any other header below.
_DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        if request.url.path not in _DOCS_PATHS:
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )
        # HSTS only makes sense once the app is actually served over
        # HTTPS — sending it over local plain HTTP would just be a lie
        # the browser can't act on.
        if get_settings().environment != "local":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


__all__ = ["SecurityHeadersMiddleware"]
