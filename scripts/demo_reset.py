"""Reset a tenant to a clean, camera-ready state.

Recording a demo means retaking it. Without this, each take leaves approved
and sent items behind and the queue looks progressively less like a fresh
inbox. This clears the tenant's events and replays a curated set of
messages through the real pipeline, so what appears on screen is what the
system actually decided - not a mock-up.

The messages are chosen to show the spread on one screen: two the knowledge
base can answer, and four held back for four different reasons, so a viewer
sees that "escalate" is a set of rules rather than a single catch-all.

Every message carries a reply address, so the Send button works on camera.

    python scripts/demo_reset.py <tenant_id> [--with-knowledge]

The knowledge base is left alone unless --with-knowledge is passed: it
rarely changes between takes, and reloading 28 documents through a hosted
connection pooler is the slowest and least reliable part of the reset.
"""
import asyncio
import datetime as dt
import pathlib
import sys

from sqlalchemy import text

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.api.triage import run_triage
from app.core.db import dispose_engine, tenant_scoped_connection
from app.core.tracing import disable_tracer
from app.models.triage import TriageRequest
from app.services.events import record_triage_decision
from app.services.ingest import KnowledgeChunk, replace_tenant_knowledge
from evals.corpus import CORPUS

# The queue lists newest first, so this list is seeded in reverse of how it
# should read on screen: the last entry here appears at the top. Reading down
# the queue then goes answered -> held, which is the order a demo narrates in,
# and leaves the most striking item (the legal threat) at the bottom as the
# closing beat. Reorder with that in mind, not alphabetically.
DEMO_MESSAGES = [
    # Held back, each for a different reason. These end up lowest on screen.
    ("The camp stove I bought burned my hand. I'm speaking to a lawyer.",
     "email", "chris@example.com"),
    ("I want a refund for the tent I bought last week, it leaked on the first night.",
     "email", "priya@example.com"),
    ("Do you sell kayaks?", "chat", "jo@example.com"),
    ("This is the third order you've delivered late. I've had enough.", "email", "alex@example.com"),
    # Answerable - the system does its job, with sources. Top of the queue.
    ("What does Trailhead Club membership cost, and what do I get for it?",
     "chat", "sam@example.com"),
    ("How long does standard shipping take, and what does it cost?", "chat", "dana@example.com"),
]


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/demo_reset.py <tenant_id>")
        sys.exit(1)
    tenant_id = sys.argv[1]
    reload_knowledge = "--with-knowledge" in sys.argv

    disable_tracer()

    try:
        async with tenant_scoped_connection(tenant_id) as conn:
            await conn.execute(
                text("delete from triage_events where tenant_id = :t"), {"t": tenant_id}
            )
        print("Cleared previous events.")

        if reload_knowledge:
            now = dt.datetime.now(dt.timezone.utc)
            loaded = await replace_tenant_knowledge(
                tenant_id,
                [
                    KnowledgeChunk(
                        c.source_id, c.title, c.content, now - dt.timedelta(days=c.age_days)
                    )
                    for c in CORPUS
                ],
            )
            print(f"Reloaded {loaded} knowledge documents.")
        print()

        for message, channel, address in DEMO_MESSAGES:
            request = TriageRequest(message=message, channel=channel, customer_email=address)
            response, model = await run_triage(request, tenant_id)
            await record_triage_decision(
                tenant_id=tenant_id,
                message=message,
                channel=channel,
                response=response,
                requested_by=None,
                latency_ms=0,
                model=model,
                customer_email=address,
            )
            mark = "HELD " if response.escalate else "draft"
            reason = response.escalation_reason or "answered with sources"
            print(f"  {mark}  {message[:46]:<46}  {reason}")

        print()
        print("Queue is camera-ready. Reload the console.")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
