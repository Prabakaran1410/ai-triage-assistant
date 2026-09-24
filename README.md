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

`POST /triage` requires a bearer token; `tenant_id` comes from it, never from
the request body. Real logins go through `GET /auth/login` -> the tenant's
own IdP via WorkOS -> `GET /auth/callback`, which needs a WorkOS Organization
mapped to a tenant first (`db/migrations/0005`). Before that's set up, or for
local testing, mint a dev-only token instead:

```bash
python scripts/seed_demo_knowledge.py     # creates a demo tenant + knowledge
python scripts/issue_test_token.py <tenant_id>
```

## Layout

```
app/
  main.py          FastAPI entrypoint
  api/             route handlers (triage, auth, health)
  core/            config, db (tenant-scoped connections), security (JWT)
  models/          pydantic schemas
  services/        retrieval, embeddings, llm, escalation, auth (WorkOS)
tests/
```

## Status

Phase 0 (foundations) mostly done: multi-tenant Postgres with enforced
row-level security, real retrieval + LLM classification/drafting pipeline,
SSO wired to WorkOS. See the project doc for the phased plan.
