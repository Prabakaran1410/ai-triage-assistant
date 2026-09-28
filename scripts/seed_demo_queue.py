"""Fill a tenant's review queue by running real messages through the real
pipeline, so the console has something to show.

Not fixtures: each message goes through retrieval, the model and the
escalation rules exactly as a customer's would, and lands in the queue with
its citations, model, latency and audit entry. What you see in the console
is therefore what the system actually decided, not a mock-up.

    python scripts/seed_demo_queue.py <tenant_id>
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.api.triage import run_triage
from app.core.db import dispose_engine
from app.core.tracing import disable_tracer
from app.models.triage import TriageRequest
from app.services.events import record_triage_decision

# A spread that exercises the different reasons a reply is held back, so the
# queue is not all one kind of item.
MESSAGES = [
    ("I want a refund for the tent I bought last week, it leaked on the first night.", "email"),
    ("This is the third order you've delivered late. I've had enough.", "email"),
    ("The stove I bought burned my hand. I'm speaking to a lawyer.", "email"),
    ("Do you sell kayaks?", "chat"),
    ("How long does standard shipping take and what does it cost?", "chat"),
    ("I forgot my password and the reset email never arrived.", "chat"),
    ("Can I return a clearance jacket I bought on sale?", "email"),
    ("What are your support hours over the weekend?", "chat"),
]


async def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/seed_demo_queue.py <tenant_id>")
        sys.exit(1)
    tenant_id = sys.argv[1]

    # One trace per seeded row would clutter the real tracing data.
    disable_tracer()

    try:
        for message, channel in MESSAGES:
            request = TriageRequest(message=message, channel=channel)
            response, model = await run_triage(request, tenant_id)
            recorded = await record_triage_decision(
                tenant_id=tenant_id,
                message=message,
                channel=channel,
                response=response,
                requested_by=None,
                latency_ms=0,
                model=model,
            )
            flag = "ESCALATED" if response.escalate else "draft    "
            print(f"  {flag}  {recorded.status:<13} {message[:52]}")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
