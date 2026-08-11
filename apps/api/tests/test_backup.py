"""Backup/restore tooling tests (Revision Prompt 16, task: backup/
restore tooling). `TestBackupRestoreRoundTrip` mirrors
`test_migrations.py`'s isolated-schema pattern — `pg_dump`/`pg_restore`
run for real against this dev Postgres server, scoped to a throwaway
schema (`pg_dump -n`), never touching `public`'s real seeded data.
Skipped, not failed, when `pg_dump`/`pg_restore` aren't discoverable on
this machine (principle 5: graceful degradation, matching every other
optional-dependency check in this project) — the round trip needs the
actual client binaries; the database itself being reachable isn't
enough.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tradingos_api.core.config import get_settings
from tradingos_api.services.backup import (
    ConnectionParams,
    find_pg_binary,
    parse_database_url,
    run_backup,
    run_restore,
)

BASE_DATABASE_URL = get_settings().database_url
SCHEMA_NAME = "backup_test_schema"


def _pg_tools_available() -> bool:
    try:
        find_pg_binary("pg_dump")
        find_pg_binary("pg_restore")
    except RuntimeError:
        return False
    return True


class TestParseDatabaseUrl:
    def test_extracts_every_field(self) -> None:
        conn = parse_database_url(
            "postgresql+psycopg://tradingos_app:s3cret@localhost:5432/tradingos"
        )
        assert conn == ConnectionParams(
            host="localhost",
            port=5432,
            user="tradingos_app",
            password="s3cret",
            dbname="tradingos",
        )

    def test_percent_encoded_password_is_decoded(self) -> None:
        # A real local `.env` password can contain characters that need
        # percent-encoding in a URL — this project already hit exactly
        # this class of bug with alembic.ini's `%`-interpolation
        # (test_migrations.py's own docstring); make_url() decodes it
        # correctly rather than passing the raw encoded form to pg_dump.
        conn = parse_database_url(
            "postgresql+psycopg://tradingos_app:a%2Fb@localhost:5432/tradingos"
        )
        assert conn.password == "a/b"

    def test_defaults_host_and_port_when_omitted(self) -> None:
        conn = parse_database_url("postgresql+psycopg://tradingos_app@/tradingos")
        assert conn.host == "localhost"
        assert conn.port == 5432

    def test_rejects_a_non_postgresql_url(self) -> None:
        with pytest.raises(ValueError, match="postgresql"):
            parse_database_url("sqlite:///local.db")


class TestFindPgBinary:
    def test_raises_a_clear_error_for_an_unknown_tool(self) -> None:
        with pytest.raises(RuntimeError, match="not found"):
            find_pg_binary("definitely-not-a-real-postgres-tool")


class TestRunRestoreValidatesInputFirst:
    def test_missing_backup_file_raises_before_touching_the_database(self) -> None:
        conn = parse_database_url(BASE_DATABASE_URL)
        with pytest.raises(FileNotFoundError):
            run_restore(conn, Path("does-not-exist.dump"))


@pytest.mark.skipif(
    not _pg_tools_available(), reason="pg_dump/pg_restore not found on this machine"
)
class TestBackupRestoreRoundTrip:
    @pytest.fixture
    def isolated_schema(self) -> Iterator[str]:
        engine = create_engine(BASE_DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {SCHEMA_NAME}"))
            conn.execute(
                text(f"CREATE TABLE {SCHEMA_NAME}.marker (id integer PRIMARY KEY, note text)")
            )
            conn.execute(text(f"INSERT INTO {SCHEMA_NAME}.marker VALUES (1, 'before-backup')"))
            conn.commit()
        try:
            yield SCHEMA_NAME
        finally:
            with engine.connect() as conn:
                conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE"))
                conn.commit()
            engine.dispose()

    def test_restore_recovers_data_after_simulated_loss(
        self, isolated_schema: str, tmp_path: Path
    ) -> None:
        conn = parse_database_url(BASE_DATABASE_URL)
        dump_path = tmp_path / "backup_test.dump"

        run_backup(conn, dump_path, extra_args=["-n", isolated_schema])
        assert dump_path.exists()
        assert dump_path.stat().st_size > 0

        engine = create_engine(BASE_DATABASE_URL)
        try:
            with engine.connect() as c:
                c.execute(text(f"DROP TABLE {isolated_schema}.marker"))
                c.commit()

            run_restore(conn, dump_path)

            with engine.connect() as c:
                row = c.execute(
                    text(f"SELECT note FROM {isolated_schema}.marker WHERE id = 1")
                ).first()
            assert row is not None
            assert row[0] == "before-backup"
        finally:
            engine.dispose()
