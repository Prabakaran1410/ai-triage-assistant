"""Map a WorkOS Organization to one of our tenants.

Until Phase 3's admin console exists, this is how a customer's WorkOS
Organization gets linked to a tenant (tenants.workos_organization_id).
Uses the admin DATABASE_URL: this is an operator action, not something the
running API does.

Usage: python scripts/map_workos_org.py <tenant_id> <workos_organization_id>
"""
import asyncio
import os
import sys

import asyncpg


async def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python scripts/map_workos_org.py <tenant_id> <workos_organization_id>")
        sys.exit(1)
    tenant_id, org_id = sys.argv[1], sys.argv[2]

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
            "update tenants set workos_organization_id = $1 where id = $2::uuid",
            org_id,
            tenant_id,
        )
    finally:
        await conn.close()

    if result == "UPDATE 0":
        print(f"No tenant with id {tenant_id}.", file=sys.stderr)
        sys.exit(1)
    print(f"Mapped WorkOS organization {org_id} -> tenant {tenant_id}")


if __name__ == "__main__":
    asyncio.run(main())
