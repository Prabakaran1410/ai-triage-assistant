from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, health, triage
from app.core.tracing import flush_tracer


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    # Render stops the container on every deploy and when the free tier
    # idles it; without this, the last few seconds of traces are lost.
    flush_tracer()


app = FastAPI(title="AI Triage Assistant", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(triage.router)
