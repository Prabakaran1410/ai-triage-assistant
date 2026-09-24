-- Phase 0: tenants, users, and row-level security.
--
-- Isolation model: every tenant-scoped table carries a `tenant_id` column and
-- an RLS policy that compares it against the Postgres session setting
-- `app.tenant_id`. The API sets that setting once per request, right after
-- opening the connection, from the authenticated caller's tenant — never
-- from a client-supplied value. A missing/empty `app.tenant_id` matches
-- nothing, so a bug that forgets to set it fails closed, not open.

create extension if not exists vector;
create extension if not exists pgcrypto;

create table if not exists tenants (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_at timestamptz not null default now()
);

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    email text not null,
    role text not null check (role in ('admin', 'reviewer', 'agent')),
    created_at timestamptz not null default now(),
    unique (tenant_id, email)
);

create table if not exists knowledge_chunks (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    source_id text not null,
    title text not null,
    content text not null,
    embedding vector(1536),
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

create table if not exists triage_events (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    message text not null,
    intent text,
    confidence real,
    escalate boolean not null default true,
    escalation_reason text,
    draft_reply text,
    reviewed_by uuid references users(id),
    reviewed_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists knowledge_chunks_tenant_idx on knowledge_chunks (tenant_id);
create index if not exists triage_events_tenant_idx on triage_events (tenant_id);
create index if not exists users_tenant_idx on users (tenant_id);

alter table users enable row level security;
alter table knowledge_chunks enable row level security;
alter table triage_events enable row level security;

drop policy if exists tenant_isolation_users on users;
create policy tenant_isolation_users on users
    using (tenant_id = current_setting('app.tenant_id', true)::uuid);

drop policy if exists tenant_isolation_knowledge_chunks on knowledge_chunks;
create policy tenant_isolation_knowledge_chunks on knowledge_chunks
    using (tenant_id = current_setting('app.tenant_id', true)::uuid);

drop policy if exists tenant_isolation_triage_events on triage_events;
create policy tenant_isolation_triage_events on triage_events
    using (tenant_id = current_setting('app.tenant_id', true)::uuid);
