"""One-time bootstrap CLI (Revision Prompt 16, ADR-066) — sets the single
seeded user's login password. Deliberately a CLI, never an HTTP
endpoint: there is no "create the first account" flow to protect
against because there is exactly one account, and it must already be
possible to run arbitrary code on this machine (a local `python -m`
invocation) to reach this at all — an HTTP endpoint that could set or
reset a password with no prior authentication would itself be the
account-takeover vulnerability this whole feature exists to close.

Run with: `python -m tradingos_api.scripts.set_password <new-password>`
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from tradingos_api.core.auth import hash_password
from tradingos_api.db.session import SessionLocal
from tradingos_api.models.identity import UserProfile


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m tradingos_api.scripts.set_password <new-password>")
        raise SystemExit(2)
    password = sys.argv[1]
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        raise SystemExit(2)

    db = SessionLocal()
    try:
        user = db.scalar(select(UserProfile))
        if user is None:
            print("No user_profile row exists — run the seed script (tradingos-seed) first.")
            raise SystemExit(1)
        user.password_hash = hash_password(password)
        db.commit()
        print(f"Password set for user {user.display_name!r} ({user.id}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
