from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, events, health, knowledge, triage
from app.core.db import dispose_engine
from app.core.tracing import flush_tracer


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    # Render stops the container on every deploy and when the free tier
    # idles it; without this, the last few seconds of traces are lost and
    # database connections are dropped rather than returned.
    flush_tracer()
    await dispose_engine()


app = FastAPI(title="AI Triage Assistant", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(triage.router)
app.include_router(events.router)
app.include_router(knowledge.router)
