"""Change a user's role.

Every user is created as `agent` by a first SSO login, deliberately: a login
should not grant the power to send replies to customers. Something has to
promote them, and until the admin console exists that something is this
script, run by an operator with the admin database URL.

Roles: admin | reviewer | agent. admin and reviewer may act on the queue;
agent may only look.

    python scripts/set_user_role.py <tenant_id> <email> <role>

Note the role is carried in the session JWT, so a promoted user must sign
out and in again before the console lets them act.
"""
import asyncio
import os
import sys

import asyncpg

VALID_ROLES = ("admin", "reviewer", "agent")


async def main() -> None:
    if len(sys.argv) != 4 or sys.argv[3] not in VALID_ROLES:
        print(f"Usage: python scripts/set_user_role.py <tenant_id> <email> [{'|'.join(VALID_ROLES)}]")
        sys.exit(1)
    tenant_id, email, role = sys.argv[1], sys.argv[2], sys.argv[3]

    database_url = os.environ.get("DATABASE_URL", "").strip("\"'")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    conn = await asyncpg.connect(
        database_url.replace("postgresql+asyncpg://", "postgresql://", 1),
        statement_cache_size=0,
    )
    try:
        result = await conn.execute(
            "update users set role = $1 where tenant_id = $2::uuid and email = $3",
            role,
            tenant_id,
            email,
        )
    finally:
        await conn.close()

    if result == "UPDATE 0":
        print(f"No user {email!r} in tenant {tenant_id}.", file=sys.stderr)
        sys.exit(1)
    print(f"{email} is now {role}. They must sign out and in again for it to take effect.")


if __name__ == "__main__":
    asyncio.run(main())
