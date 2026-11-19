"""Manage dashboard logins from the VPS.

  .venv/bin/python -m papillon.users add sachin@theingredientlist.co "Sachin" agency
  .venv/bin/python -m papillon.users add sales@papillon.in "Papillon Sales" papillon
  .venv/bin/python -m papillon.users password sales@papillon.in
  .venv/bin/python -m papillon.users remove sales@papillon.in
  .venv/bin/python -m papillon.users list
"""

import asyncio
import getpass
import sys

from . import db
from .auth import hash_password


def _ask_password() -> str:
    while True:
        a = getpass.getpass("Password (8+ characters): ")
        if len(a) < 8:
            print("Too short.")
            continue
        if a == getpass.getpass("Same again: "):
            return a
        print("Didn't match, try again.")


async def main(args: list[str]) -> None:
    await db.open_pool()
    try:
        cmd = args[0] if args else "list"
        if cmd == "add":
            email, name, org = args[1], args[2], args[3]
            if org not in ("agency", "papillon"):
                sys.exit("org must be agency or papillon")
            await db.execute(
                """insert into team_members (email, name, org, role, password_hash) values (%s,%s,%s,%s,%s)
                   on conflict (email) do update set name = excluded.name, org = excluded.org,
                     password_hash = excluded.password_hash, active = true""",
                [email.lower(), name, org, "admin" if org == "agency" else "sales", hash_password(_ask_password())])
            print(f"Added {email} ({org})")
        elif cmd == "password":
            await db.execute("update team_members set password_hash = %s where lower(email) = lower(%s)",
                             [hash_password(_ask_password()), args[1]])
            print("Password changed")
        elif cmd == "remove":
            await db.execute("update team_members set active = false where lower(email) = lower(%s)", [args[1]])
            print("Login disabled")
        else:
            for u in await db.fetchall("select email, name, org, active from team_members order by org, email"):
                print(f"{u['email']:40} {u['org']:10} {'active' if u['active'] else 'disabled'}  {u['name'] or ''}")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
