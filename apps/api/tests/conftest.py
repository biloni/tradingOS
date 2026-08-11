"""Shared fixtures for API/model tests.

`db_session` wraps each test in an outer transaction against the *real*
dev Postgres database (the one `docker-compose`/local Postgres already
seeds) and rolls it back afterward. Router code calls `db.commit()`
internally; `join_transaction_mode="create_savepoint"` (SQLAlchemy 2.0)
downgrades those inner commits to SAVEPOINT releases so the outer
transaction — and therefore the rollback — stays in control. This means
every test in this file can freely INSERT/UPDATE through the real routers
without ever touching the seeded dev data other tests and manual
verification rely on.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from tradingos_api.core.auth import hash_password
from tradingos_api.core.config import get_settings
from tradingos_api.db.session import get_db
from tradingos_api.main import app
from tradingos_api.models.enums import AccountType
from tradingos_api.models.execution import Account
from tradingos_api.models.identity import UserProfile
from tradingos_api.routers.auth import login_rate_limiter

# Revision Prompt 16, ADR-066 — never a real credential; set once on the
# seeded user inside each test's own rolled-back transaction. The
# `client` fixture logs in with this automatically so none of the
# pre-existing tests need to change just to get past the new auth gate.
TEST_PASSWORD = "test-password-not-a-real-secret"

_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url)
    return _engine


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = _get_engine()
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """Revision Prompt 16, ADR-066: sets a test-only password on the
    seeded user and logs in before yielding, so the returned
    `TestClient` already carries a valid session cookie (httpx's
    client-level cookie jar persists it across every subsequent request
    the test makes) — no change needed in any of the ~600 tests that
    already assumed an unauthenticated `client` could call any route."""

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        user = db_session.scalar(select(UserProfile))
        if user is not None:
            user.password_hash = hash_password(TEST_PASSWORD)
            db_session.flush()
        test_client = TestClient(app)
        if user is not None:
            # `login_rate_limiter` is a module-level singleton shared by
            # the whole pytest process (Revision Prompt 16) — every test
            # logging in once would otherwise exhaust it after 5 tests.
            login_rate_limiter.reset()
            login_response = test_client.post(
                "/api/v1/auth/login", json={"password": TEST_PASSWORD}
            )
            assert login_response.status_code == 200, login_response.text
        yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def seeded_user_id(db_session: Session) -> uuid.UUID:
    row = db_session.execute(text("SELECT id FROM user_profile LIMIT 1")).first()
    assert row is not None, "seed data must exist (run `tradingos-seed`)"
    return cast(uuid.UUID, row[0])


@pytest.fixture
def seeded_instrument_id(db_session: Session) -> uuid.UUID:
    row = db_session.execute(text("SELECT id FROM instruments LIMIT 1")).first()
    assert row is not None
    return cast(uuid.UUID, row[0])


@pytest.fixture
def fresh_account(db_session: Session, seeded_user_id: uuid.UUID) -> Account:
    """A brand-new MANUAL account, isolated per-test by `db_session`'s
    rollback — safe to post fills against without touching seeded data."""
    account = Account(
        account_type=AccountType.MANUAL,
        name=f"Test Account {uuid.uuid4()}",
        owner_user_id=seeded_user_id,
    )
    db_session.add(account)
    db_session.flush()
    return account
