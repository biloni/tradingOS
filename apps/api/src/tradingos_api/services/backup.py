"""Postgres backup/restore tooling (Revision Prompt 16, task: backup/
restore tooling). Thin wrapper over `pg_dump`/`pg_restore` — this
project deliberately doesn't reimplement dump/restore logic itself, the
same "don't build what a battle-tested external tool already does
correctly" call `docs/BLOCKING_DECISIONS.md` #4 made for the scheduler
(APScheduler, not a hand-rolled timer loop).

Custom format (`pg_dump -Fc`) rather than plain SQL: compressed, and
lets `pg_restore --clean --if-exists` do a safe "drop what exists, then
recreate" restore without needing `tradingos_app` to have `CREATEDB`
(it doesn't — verified in `tests/test_migrations.py`'s own docstring).
Every restore targets the existing database by name, never creates a
new one.

`pg_dump`/`pg_restore` aren't reliably on `PATH` on a native Windows
Postgres install (this project's own dev machine: only under
`C:\\Program Files\\PostgreSQL\\16\\bin\\`) — `find_pg_binary()` checks
`PATH` first, then that Windows install location, so this still works
unmodified on a machine where the tools *are* on `PATH` (Linux/macOS,
or a Windows box with `PATH` configured).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url

# pg_dump/pg_restore run against a real database over the network — long
# enough to cover a large personal-project database without hanging
# forever on a genuinely stuck connection.
_SUBPROCESS_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class ConnectionParams:
    host: str
    port: int
    user: str
    password: str | None
    dbname: str


def parse_database_url(url: str) -> ConnectionParams:
    """`Settings.database_url`'s `postgresql+psycopg://...` form, decoded
    into the discrete pieces `pg_dump`/`pg_restore`'s CLI flags need.
    Uses SQLAlchemy's own `make_url()` rather than hand-rolled URL
    parsing — it already handles percent-decoding correctly (a real
    local `.env` password can contain characters needing it) and the
    `+psycopg` driver suffix, both of which a naive `urllib.parse` split
    would need to reimplement."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        raise ValueError(f"Not a postgresql database URL: {url}")
    return ConnectionParams(
        host=parsed.host or "localhost",
        port=parsed.port or 5432,
        user=parsed.username or "",
        password=parsed.password,
        dbname=parsed.database or "",
    )


def find_pg_binary(name: str) -> str:
    """`name` is e.g. `"pg_dump"` or `"pg_restore"` (no `.exe` suffix —
    added automatically on Windows). Checks `PATH` first, then this
    project's own dev machine's known native-install location. Raises a
    clear, actionable error rather than letting `subprocess.run` fail
    with an opaque `FileNotFoundError` deeper in the call stack
    (principle 5: graceful, honest degradation)."""
    on_path = shutil.which(name)
    if on_path:
        return on_path

    if sys.platform == "win32":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        pg_root = program_files / "PostgreSQL"
        if pg_root.is_dir():
            candidates = sorted(pg_root.glob(f"*/bin/{name}.exe"), reverse=True)
            if candidates:
                return str(candidates[0])
        raise RuntimeError(
            f"{name} not found on PATH or under {pg_root}\\<version>\\bin\\. "
            "Install the PostgreSQL client tools, or add them to PATH."
        )
    raise RuntimeError(f"{name} not found on PATH. Install the PostgreSQL client tools.")


def run_backup(
    conn: ConnectionParams, output_path: Path, *, extra_args: Sequence[str] = ()
) -> None:
    """Runs `pg_dump -Fc` (custom format). `extra_args` lets a caller
    scope the dump (e.g. `["-n", "some_schema"]`) — used by
    `tests/test_backup.py`'s round-trip test to dump/restore a
    throwaway schema instead of the real `public` schema's data; the
    CLI script (`scripts/backup_db.py`) never passes any, backing up
    the whole database."""
    pg_dump = find_pg_binary("pg_dump")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PGPASSWORD": conn.password or ""}
    args = [
        pg_dump,
        "-h",
        conn.host,
        "-p",
        str(conn.port),
        "-U",
        conn.user,
        "-d",
        conn.dbname,
        "-Fc",
        "-f",
        str(output_path),
        *extra_args,
    ]
    result = subprocess.run(
        args,
        env=env,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed (exit {result.returncode}):\n{result.stderr}")


def run_restore(
    conn: ConnectionParams, input_path: Path, *, extra_args: Sequence[str] = ()
) -> None:
    """Runs `pg_restore --clean --if-exists --no-owner` against the
    existing database named in `conn` — never creates a new database
    (`tradingos_app` has no `CREATEDB` privilege). `--clean --if-exists`
    drops each object the dump contains before recreating it, so this is
    safe to run against a target that already has some or all of the
    dumped objects, not just an empty one."""
    if not input_path.exists():
        raise FileNotFoundError(f"Backup file not found: {input_path}")
    pg_restore = find_pg_binary("pg_restore")
    env = {**os.environ, "PGPASSWORD": conn.password or ""}
    args = [
        pg_restore,
        "-h",
        conn.host,
        "-p",
        str(conn.port),
        "-U",
        conn.user,
        "-d",
        conn.dbname,
        "--clean",
        "--if-exists",
        "--no-owner",
        *extra_args,
        str(input_path),
    ]
    result = subprocess.run(
        args,
        env=env,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_restore failed (exit {result.returncode}):\n{result.stderr}")


__all__ = [
    "ConnectionParams",
    "find_pg_binary",
    "parse_database_url",
    "run_backup",
    "run_restore",
]
