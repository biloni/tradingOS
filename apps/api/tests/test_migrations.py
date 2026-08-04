"""Migration reversibility tests (docs/TASKS.md Phase 8 requirement).

Runs the full Alembic chain against an *isolated Postgres schema* on the
same server the app already uses, never against the `public` schema that
holds real seeded dev data. Isolation is via the `PGOPTIONS` env var
(`-c search_path=...`, see `_run_alembic`), not a second database, because
the `tradingos_app` role has no CREATEDB privilege in this environment
(verified during Phase 8) — schema CREATE/DROP is granted, so that's the
isolation unit instead.

Each alembic invocation is a fresh subprocess so `core.config.get_settings()`
(`lru_cache`d) picks up the schema-scoped `DATABASE_URL` cleanly.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tradingos_api.core.config import get_settings

API_DIR = Path(__file__).resolve().parent.parent
SCHEMA_NAME = "migration_test_schema"
BASE_DATABASE_URL = get_settings().database_url

# Representative sample, not exhaustive: one table per bounded context.
# Present after `upgrade head` (includes 3 names reused-with-reshaped-columns
# from the old MVP schema: recommendations, backtest_runs, audit_events).
NEW_SCHEMA_TABLES = {
    "user_profile",
    "instruments",
    "watchlist_items",
    "market_bars",
    "committee_sessions",
    "recommendations",
    "accounts",
    "orders",
    "position_lots",
    "recommendation_outcomes",
    "backtest_runs",
    "audit_events",
    "job_runs",
}
# Table names that exist ONLY in the new Phase 8 schema — excludes the 3
# reused names above, since those are legitimately present both before and
# after the Phase 8 migration and would break an isdisjoint() check.
NEW_SCHEMA_ONLY_TABLES = NEW_SCHEMA_TABLES - {"recommendations", "backtest_runs", "audit_events"}
OLD_MVP_ONLY_TABLES = {"symbols", "price_bars", "paper_portfolios", "paper_orders"}


def _run_alembic(*args: str, schema: str) -> None:
    # PGOPTIONS (a libpq-recognized env var) scopes every connection this
    # subprocess makes to `schema`'s search_path, without needing to encode
    # `-c search_path=...` into DATABASE_URL itself — alembic.ini's
    # ConfigParser applies `%`-interpolation to the url string, which chokes
    # on percent-encoded query params (`%20`, `%3D`) with an "invalid
    # interpolation syntax" error.
    env = {
        **os.environ,
        "DATABASE_URL": BASE_DATABASE_URL,
        "PGOPTIONS": f"-c search_path={schema}",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(args)} failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def _tables_in_schema(schema: str) -> set[str]:
    engine = create_engine(BASE_DATABASE_URL)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"),
                {"s": schema},
            )
            return {r[0] for r in rows}
    finally:
        engine.dispose()


@pytest.fixture
def isolated_schema() -> Iterator[str]:
    engine = create_engine(BASE_DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA_NAME}"))
        conn.commit()
    try:
        yield SCHEMA_NAME
    finally:
        with engine.connect() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE"))
            conn.commit()
        engine.dispose()


def test_upgrade_from_empty_reaches_head(isolated_schema: str) -> None:
    _run_alembic("upgrade", "head", schema=isolated_schema)
    tables = _tables_in_schema(isolated_schema)
    assert NEW_SCHEMA_TABLES.issubset(tables)
    assert tables.isdisjoint(OLD_MVP_ONLY_TABLES)
    assert "alembic_version" in tables


def test_downgrade_one_step_restores_pre_phase8_schema(isolated_schema: str) -> None:
    _run_alembic("upgrade", "head", schema=isolated_schema)
    _run_alembic("downgrade", "eed7cb451bdc", schema=isolated_schema)
    tables = _tables_in_schema(isolated_schema)
    assert OLD_MVP_ONLY_TABLES.issubset(tables)
    assert tables.isdisjoint(NEW_SCHEMA_ONLY_TABLES)


def test_upgrade_downgrade_upgrade_round_trip(isolated_schema: str) -> None:
    _run_alembic("upgrade", "head", schema=isolated_schema)
    _run_alembic("downgrade", "eed7cb451bdc", schema=isolated_schema)
    _run_alembic("upgrade", "head", schema=isolated_schema)
    tables = _tables_in_schema(isolated_schema)
    assert NEW_SCHEMA_TABLES.issubset(tables)


def test_downgrade_to_base_empties_schema(isolated_schema: str) -> None:
    _run_alembic("upgrade", "head", schema=isolated_schema)
    _run_alembic("downgrade", "base", schema=isolated_schema)
    tables = _tables_in_schema(isolated_schema)
    # Alembic never drops its own bookkeeping table on `downgrade base` —
    # it just deletes the (single) version row, so this is the true empty
    # state, not a leftover.
    assert tables == {"alembic_version"}
    engine = create_engine(BASE_DATABASE_URL)
    try:
        with engine.connect() as conn:
            count = conn.execute(
                text(f'SELECT count(*) FROM "{isolated_schema}".alembic_version')
            ).scalar()
        assert count == 0
    finally:
        engine.dispose()
