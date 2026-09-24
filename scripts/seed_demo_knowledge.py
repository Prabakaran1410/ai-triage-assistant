"""Seed one demo tenant with a handful of knowledge chunks and real
embeddings, so /triage has something to retrieve against.

Usage: python scripts/seed_demo_knowledge.py
Requires APP_DATABASE_URL and GOOGLE_API_KEY in the environment.
Prints the demo tenant_id to use when calling POST /triage.
"""
import asyncio
import datetime as dt
import pathlib
import sys
import uuid

from sqlalchemy import text

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.core.db import get_engine, tenant_scoped_connection
from app.services.embeddings import embed_text

DEMO_CHUNKS = [
    (
        "refund-policy",
        "Refund Policy",
        (
            "Refunds are issued within 5 business days of an approved request. "
            "Requests must be made within 30 days of purchase. Digital products "
            "are non-refundable once downloaded."
        ),
    ),
    (
        "support-hours",
        "Support Hours",
        (
            "Support is available Monday to Friday, 9am to 6pm in the "
            "customer's local timezone. Messages sent outside these hours are "
            "answered the next business day."
        ),
    ),
    (
        "pricing-plans",
        "Pricing Plans",
        (
            "The Starter plan is $29/month for up to 3 users. The Growth plan "
            "is $99/month for up to 15 users and includes priority support."
        ),
    ),
]


async def main() -> None:
    engine = get_engine()
    tenant_id = uuid.uuid4()

    async with engine.begin() as conn:
        await conn.execute(
            text("insert into tenants (id, name) values (:id, :name)"),
            {"id": str(tenant_id), "name": "Demo Tenant"},
        )

    async with tenant_scoped_connection(str(tenant_id)) as conn:
        for source_id, title, content in DEMO_CHUNKS:
            embedding = await embed_text(content, task_type="RETRIEVAL_DOCUMENT")
            await conn.execute(
                text(
                    """
                    insert into knowledge_chunks
                        (tenant_id, source_id, title, content, embedding, updated_at)
                    values
                        (:tenant_id, :source_id, :title, :content, (:embedding)::vector, :updated_at)
                    """
                ),
                {
                    "tenant_id": str(tenant_id),
                    "source_id": source_id,
                    "title": title,
                    "content": content,
                    "embedding": str(embedding),
                    "updated_at": dt.datetime.now(dt.timezone.utc),
                },
            )

    print(f"Seeded {len(DEMO_CHUNKS)} chunks for demo tenant: {tenant_id}")
    print()
    print("/triage now requires a bearer token (tenant_id comes from it, not the body).")
    print("Mint a dev test token for this tenant (bypasses real WorkOS SSO - see")
    print("scripts/issue_test_token.py for why this exists):")
    print(f"  python scripts/issue_test_token.py {tenant_id}")
    print()
    print("Then:")
    print(
        '  curl -X POST <api-url>/triage -H "Content-Type: application/json" '
        '-H "Authorization: Bearer <token>" '
        '-d \'{"message": "How much does the Growth plan cost?"}\''
    )


if __name__ == "__main__":
    asyncio.run(main())
