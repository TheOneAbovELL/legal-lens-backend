"""Create a user (for deployments with AUTH_ALLOW_REGISTRATION=false).

    python scripts/create_user.py --username alice --role advocate
The password is read interactively (never pass secrets on the command line).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.repositories import UserRepository  # noqa: E402
from app.db.session import Database  # noqa: E402


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--username", required=True)
    p.add_argument("--email")
    p.add_argument("--role", choices=["citizen", "advocate", "researcher"], default="citizen")
    args = p.parse_args()
    password = getpass.getpass("Password: ")
    if len(password) < 8 or password != getpass.getpass("Repeat password: "):
        print("passwords must match and be at least 8 characters")
        return 1
    db = Database(get_settings().database_url)
    try:
        await db.migrate()
        async with db.sessions() as session:
            user = await UserRepository(session).create(
                username=args.username, email=args.email, password_hash=hash_password(password), role=args.role
            )
        print(f"created user {user.username} ({user.role}) id={user.id}")
    finally:
        await db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
