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
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.db.session import get_db
from tradingos_api.main import app
from tradingos_api.models.enums import AccountType
from tradingos_api.models.execution import Account

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
    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
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
