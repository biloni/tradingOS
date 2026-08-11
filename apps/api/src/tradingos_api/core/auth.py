"""Password hashing and session management (Revision Prompt 16, ADR-066).

Stdlib-only, deliberately: `hashlib.scrypt` (PEP 3156-era, available
since Python 3.6) needs no new dependency for a single-user app, and
`secrets`/`hmac` cover everything else. No third-party auth framework —
there is exactly one user, exactly one login form, exactly one session
type; a full OAuth/JWT stack would be solving a multi-tenant problem
this app doesn't have.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from tradingos_api.models.identity import Session as SessionModel
from tradingos_api.models.identity import UserProfile

SESSION_COOKIE_NAME = "tradingos_session"
SESSION_TTL = timedelta(hours=12)

# Double-submit CSRF cookie (Revision Prompt 16, ADR-066 follow-up). This
# cookie is deliberately NOT httpOnly — the frontend must be able to read
# it and echo it back as a header, which is the entire point of the
# pattern: SOP means a cross-origin attacker page can't read *this*
# origin's cookie value to forge the header, even though the browser
# would still auto-attach the (httpOnly) session cookie to a forged
# cross-origin request. Stateless by design (no server-side storage,
# nothing to look up) — the check is just "does the header equal the
# cookie", which is exactly what defeats a same-origin-blind forger.
CSRF_COOKIE_NAME = "tradingos_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
_CSRF_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Step-up auth (task: kill switch / cancel-all / mode changes / approval
# decisions) requires the password to have been re-entered within this
# window — deliberately much shorter than SESSION_TTL, since "logged in
# this morning" and "confirmed this specific destructive action just
# now" are different facts (Prompt 16's own "step-up authentication
# where practical" requirement).
STEP_UP_TTL = timedelta(minutes=5)

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """`scrypt$<salt_hex>$<hash_hex>` — never a plaintext password or a
    reversible cipher. Cost parameters chosen to keep a login request
    under ~100ms on ordinary hardware while still being far more
    expensive than a fast hash (MD5/SHA) that GPU-cracks trivially."""
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison of the derived hash — `hmac.compare_digest`,
    never `==`, so response timing can't leak how many hash bytes matched."""
    try:
        scheme, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(hash_hex)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    return hmac.compare_digest(derived, expected)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf_token(request: Request) -> None:
    """Enforced on every state-changing request to an authenticated route
    (called from `core/dependencies.py::require_session()`) and, since
    `/auth/logout` and `/auth/step-up` aren't gated by `require_session`
    (a valid session cookie alone isn't required to attempt those), from
    those two handlers directly. GET/HEAD/OPTIONS are exempt — CSRF
    protects state changes, not reads. Login is never subject to this
    check: no session/CSRF cookie pair exists yet at that point."""
    if request.method in _CSRF_SAFE_METHODS:
        return
    header_value = request.headers.get(CSRF_HEADER_NAME)
    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    if not header_value or not cookie_value or not hmac.compare_digest(header_value, cookie_value):
        raise HTTPException(status_code=403, detail="Missing or invalid CSRF token.")


def _hash_token(raw_token: str) -> str:
    """SHA-256 of the session token — what's actually stored in
    `sessions.token_hash`. The raw token itself only ever exists in the
    client's httpOnly cookie and the single login response; a database
    dump alone can never be replayed as a live session."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CreatedSession:
    raw_token: str
    session_id: uuid.UUID
    expires_at: datetime


def create_session(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    user_agent: str | None,
    ip_address: str | None,
) -> CreatedSession:
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    session = SessionModel(
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        expires_at=now + SESSION_TTL,
        last_seen_at=now,
        user_agent=user_agent[:255] if user_agent else None,
        ip_address=ip_address,
    )
    db.add(session)
    db.flush()
    return CreatedSession(raw_token=raw_token, session_id=session.id, expires_at=session.expires_at)


def get_valid_session(db: DbSession, *, raw_token: str) -> SessionModel | None:
    """Looks up a session by the raw token's hash and returns it only if
    still valid (not expired, not revoked) — never touches
    `last_seen_at` itself (that's the caller's job, once per request, so
    a read-only lookup used for a dry-run check doesn't silently extend
    a session's activity trail)."""
    token_hash = _hash_token(raw_token)
    session = db.scalar(select(SessionModel).where(SessionModel.token_hash == token_hash))
    if session is None:
        return None
    now = datetime.now(UTC)
    if session.revoked_at is not None:
        return None
    if session.expires_at <= now:
        return None
    return session


def touch_session(db: DbSession, session: SessionModel) -> None:
    session.last_seen_at = datetime.now(UTC)
    db.flush()


def revoke_session(db: DbSession, session: SessionModel) -> None:
    session.revoked_at = datetime.now(UTC)
    db.flush()


def mark_stepped_up(db: DbSession, session: SessionModel) -> None:
    session.stepped_up_at = datetime.now(UTC)
    db.flush()


def is_step_up_fresh(stepped_up_at: datetime | None) -> bool:
    """The raw-timestamp form — used by `core/dependencies.py::require_step_up()`,
    which only has `request.state.stepped_up_at` (a plain timestamp
    copied off the session row by `require_session()`), not a full
    `Session` ORM instance to pass to `is_stepped_up()` below."""
    if stepped_up_at is None:
        return False
    return datetime.now(UTC) - stepped_up_at <= STEP_UP_TTL


def is_stepped_up(session: SessionModel) -> bool:
    return is_step_up_fresh(session.stepped_up_at)


def get_user(db: DbSession, user_id: uuid.UUID) -> UserProfile | None:
    return db.get(UserProfile, user_id)


def get_default_user_id(db: DbSession) -> uuid.UUID:
    """ "The app's one user" (ADR-007's single-user premise, still true
    post-ADR-066) — for internal service code that runs outside any HTTP
    request context (e.g. `services/committee_orchestrator.py`, which
    has no `Request` to read a session from) and genuinely needs "the
    owner," not "the currently authenticated session." Deliberately
    separate from `core/dependencies.py::get_current_user_id()`, which
    only ever reads an already-validated session's `request.state` and
    must never be called outside a request — conflating the two
    was the exact bug this function exists to fix (a pre-Revision-Prompt-16
    call site was calling the session-reading function directly as a
    plain Python function, which broke the moment sessions became real)."""
    user = db.scalar(select(UserProfile))
    if user is None:
        raise ValueError("No user_profile row exists — run the seed script (tradingos-seed).")
    return user.id
