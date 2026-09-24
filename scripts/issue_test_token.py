"""Mint a JWT directly, bypassing WorkOS - for local testing only.

The real path is GET /auth/login -> customer's IdP -> GET /auth/callback,
which needs a WorkOS Organization with a configured SSO connection mapped to
a tenant (db/migrations/0005). Setting that up is a separate manual step;
this script exists so /triage's auth requirement can be tested before that's
done, without ever exposing token-minting as an HTTP endpoint.

Usage: python scripts/issue_test_token.py <tenant_id> [email] [role]
Requires JWT_SECRET in the environment (must match what the API uses).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.services.auth import issue_jwt


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/issue_test_token.py <tenant_id> [email] [role]")
        sys.exit(1)

    tenant_id = sys.argv[1]
    email = sys.argv[2] if len(sys.argv) > 2 else "dev-tester@example.com"
    role = sys.argv[3] if len(sys.argv) > 3 else "agent"

    token = issue_jwt(user_id="dev-test-user", email=email, tenant_id=tenant_id, role=role)
    print(token)


if __name__ == "__main__":
    main()
