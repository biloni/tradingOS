"""Restore the TradingOS Postgres database from a `pg_dump` custom-format
backup (Revision Prompt 16, task: backup/restore tooling). **DESTRUCTIVE**
— drops and recreates every object the backup file contains, overwriting
whatever is currently in the target database. Wraps
`pg_restore --clean --if-exists --no-owner` via `services/backup.py`.

Run with:
`python -m tradingos_api.scripts.restore_db <backup-path> [--yes]`

Prompts for a typed "yes" confirmation naming the exact target database
before doing anything, unless `--yes` is passed (for scripted/CI use).
"""

from __future__ import annotations

import sys
from pathlib import Path

from tradingos_api.core.config import get_settings
from tradingos_api.services.backup import parse_database_url, run_restore

_USAGE = "Usage: python -m tradingos_api.scripts.restore_db <backup-path> [--yes]"


def main() -> None:
    args = sys.argv[1:]
    skip_confirm = "--yes" in args
    positional = [a for a in args if a != "--yes"]
    if len(positional) != 1:
        print(_USAGE)
        raise SystemExit(1)
    input_path = Path(positional[0])

    conn = parse_database_url(get_settings().database_url)

    if not skip_confirm:
        answer = input(
            f"This will DROP and restore objects in database '{conn.dbname}' on "
            f"{conn.host}:{conn.port} from {input_path}. Existing data in those "
            f"objects will be overwritten. Type 'yes' to continue: "
        )
        if answer.strip().lower() != "yes":
            print("Aborted.")
            raise SystemExit(1)

    print(f"Restoring database '{conn.dbname}' from {input_path} ...")
    run_restore(conn, input_path)
    print("Restore complete.")


if __name__ == "__main__":
    main()
