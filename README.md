# AI Triage Assistant

Classifies inbound customer messages, retrieves cited facts from a knowledge base,
drafts a reply, and escalates to a human instead of guessing when unsure.

Full plan, architecture, decisions log, and status live in the project doc (not in
this repo): ask the maintainer for the current link.

## Quickstart

```bash
cp .env.example .env
docker compose up --build
```

API comes up at `http://localhost:8000`. Health check: `GET /healthz`.

## Layout

```
app/
  main.py          FastAPI entrypoint
  api/             route handlers (triage, ask, admin)
  core/            config, security, tenancy
  models/          pydantic schemas
  services/        retrieval, classification, drafting, escalation
tests/
```

## Status

Phase 0 (foundations) in progress. See the project doc for the phased plan.
