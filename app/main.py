from fastapi import FastAPI

from app.api import health, triage

app = FastAPI(title="AI Triage Assistant", version="0.1.0")

app.include_router(health.router)
app.include_router(triage.router)
