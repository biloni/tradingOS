"""Login, logout, session status, and step-up re-authentication
(Revision Prompt 16, ADR-066). `POST /login` and `GET /session` are the
only two routes in this entire API never gated by
`core/dependencies.py::require_session()` (`main.py` omits it from this
router's `include_router()` call) — `/logout` and `/step-up` are *also*
excluded from that dependency (a client with an expired-but-not-yet-
cleared session cookie must still be able to reach `/logout`), so both
validate the session cookie manually below and separately call
`verify_csrf_token()` themselves, since they're state-changing but never
pass through `require_session()`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from tradingos_api.core.auth import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SESSION_TTL,
    create_session,
    generate_csrf_token,
    get_valid_session,
    is_stepped_up,
    mark_stepped_up,
    revoke_session,
    verify_csrf_token,
    verify_password,
)
from tradingos_api.core.config import get_settings
from tradingos_api.core.rate_limit import TokenBucketRateLimiter
from tradingos_api.db.session import get_db
from tradingos_api.models.identity import UserProfile
from tradingos_api.schemas.auth import LoginRequest, SessionStatusResponse, StepUpRequest

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# 5-attempt burst, 1/min steady-state refill — slows a brute-force
# guess loop against the single password to a crawl without needing
# Redis or any shared state beyond this process (same reasoning as
# `core/rate_limit.py::ask_rate_limiter`).
login_rate_limiter = TokenBucketRateLimiter(capacity=5, refill_per_second=1 / 60)

# Revision Prompt 16 threat-model review (ADR-069): `/step-up` re-checks
# the same password as `/login` but was never rate-limited — an attacker
# holding a stolen (or CSRF'd, before ADR-067) session+CSRF cookie pair
# could otherwise brute-force the password here with no throttle at all,
# since `require_session`'s auth gate doesn't apply to this route (see
# module docstring). Same bucket shape as `login_rate_limiter`, kept as
# a separate instance so a login lockout and a step-up lockout don't
# share (or fight over) the same budget.
step_up_rate_limiter = TokenBucketRateLimiter(capacity=5, refill_per_second=1 / 60)


def _set_auth_cookies(response: Response, *, raw_token: str, csrf_token: str) -> None:
    settings = get_settings()
    secure = settings.environment != "local"
    response.set_cookie(
        SESSION_COOKIE_NAME,
        raw_token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
    )
    # Deliberately NOT httpOnly — the frontend reads this and echoes it
    # back as the `X-CSRF-Token` header (double-submit pattern, see
    # `core/auth.py::verify_csrf_token`'s docstring for why that's safe).
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        samesite="lax",
        secure=secure,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


@router.post("/login", response_model=SessionStatusResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> SessionStatusResponse:
    if not login_rate_limiter.try_acquire():
        raise HTTPException(
            status_code=429, detail="Too many login attempts — wait a moment and try again."
        )

    user = db.scalar(select(UserProfile))
    if user is None or user.password_hash is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "No password is configured for this account. Run "
                "`python -m tradingos_api.scripts.set_password <password>` first."
            ),
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    created = create_session(
        db,
        user_id=user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    _set_auth_cookies(response, raw_token=created.raw_token, csrf_token=generate_csrf_token())
    return SessionStatusResponse(
        authenticated=True, stepped_up=False, expires_at=created.expires_at.isoformat()
    )


@router.post("/logout", response_model=SessionStatusResponse)
def logout(
    request: Request, response: Response, db: DbSession = Depends(get_db)
) -> SessionStatusResponse:
    verify_csrf_token(request)
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if raw_token:
        session = get_valid_session(db, raw_token=raw_token)
        if session is not None:
            revoke_session(db, session)
            db.commit()
    _clear_auth_cookies(response)
    return SessionStatusResponse(authenticated=False)


@router.get("/session", response_model=SessionStatusResponse)
def session_status(request: Request, db: DbSession = Depends(get_db)) -> SessionStatusResponse:
    """Public (exempt from the auth-gate middleware) — this is how the
    frontend discovers whether to show a login screen at all. Never
    leaks anything beyond authenticated/stepped-up/expiry."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        return SessionStatusResponse(authenticated=False)
    session = get_valid_session(db, raw_token=raw_token)
    if session is None:
        return SessionStatusResponse(authenticated=False)
    return SessionStatusResponse(
        authenticated=True,
        stepped_up=is_stepped_up(session),
        expires_at=session.expires_at.isoformat(),
    )


@router.post("/step-up", response_model=SessionStatusResponse)
def step_up(
    payload: StepUpRequest, request: Request, db: DbSession = Depends(get_db)
) -> SessionStatusResponse:
    """Re-verifies the password against the already-authenticated
    session — the step-up requirement for kill switch / cancel-all /
    mode changes / approval decisions. Not gated by `require_session()`
    (see module docstring), so both the session and the CSRF token are
    validated here directly."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    session = get_valid_session(db, raw_token=raw_token) if raw_token else None
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    verify_csrf_token(request)

    if not step_up_rate_limiter.try_acquire():
        raise HTTPException(
            status_code=429, detail="Too many step-up attempts — wait a moment and try again."
        )

    user = db.get(UserProfile, session.user_id)
    if (
        user is None
        or user.password_hash is None
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    mark_stepped_up(db, session)
    db.commit()
    return SessionStatusResponse(
        authenticated=True, stepped_up=True, expires_at=session.expires_at.isoformat()
    )


__all__ = ["router"]
