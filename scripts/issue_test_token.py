"""Mint a JWT directly, bypassing WorkOS - for local testing only.

The real path is GET /auth/login -> customer's IdP -> GET /auth/callback,
which needs a WorkOS Organization with a configured SSO connection mapped to
a tenant (db/migrations/0005). This script exists so the API can be exercised
without that, and it is never exposed as an HTTP endpoint.

It creates a real `users` row (like a real login does) rather than inventing
an id, because triage_events.requested_by is a foreign key to users: the
audit trail is only worth having if the actor on a record resolves to
somebody real.

Usage: python scripts/issue_test_token.py <tenant_id> [email] [role]
Requires JWT_SECRET and APP_DATABASE_URL in the environment.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.core.db import dispose_engine
from app.services.auth import issue_jwt, upsert_user


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/issue_test_token.py <tenant_id> [email] [role]")
        sys.exit(1)

    tenant_id = sys.argv[1]
    email = sys.argv[2] if len(sys.argv) > 2 else "dev-tester@example.com"

    try:
        user_id, role = await upsert_user(tenant_id, email)
        if len(sys.argv) > 3:
            role = sys.argv[3]
        print(issue_jwt(user_id=user_id, email=email, tenant_id=tenant_id, role=role))
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
