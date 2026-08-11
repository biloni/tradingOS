"""Back up the TradingOS Postgres database (Revision Prompt 16, task:
backup/restore tooling). Wraps `pg_dump` (custom format) via
`services/backup.py`.

Run with:
`python -m tradingos_api.scripts.backup_db [output-path]`

`output-path` defaults to `apps/api/backups/tradingos_<UTC timestamp>.dump`
(that directory is gitignored — a backup file is local operational
data, never committed).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from tradingos_api.core.config import get_settings
from tradingos_api.services.backup import parse_database_url, run_backup

# apps/api/ — three levels up from this file (scripts/ -> tradingos_api/ -> src/).
_API_DIR = Path(__file__).resolve().parents[3]
DEFAULT_BACKUPS_DIR = _API_DIR / "backups"


def main() -> None:
    if len(sys.argv) > 2:
        print("Usage: python -m tradingos_api.scripts.backup_db [output-path]")
        raise SystemExit(1)

    if len(sys.argv) == 2:
        output_path = Path(sys.argv[1])
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_path = DEFAULT_BACKUPS_DIR / f"tradingos_{timestamp}.dump"

    conn = parse_database_url(get_settings().database_url)
    print(f"Backing up database '{conn.dbname}' on {conn.host}:{conn.port} to {output_path} ...")
    run_backup(conn, output_path)
    size_kb = output_path.stat().st_size / 1024
    print(f"Backup complete: {output_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
