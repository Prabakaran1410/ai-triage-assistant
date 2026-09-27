-- Make triage results a system of record, and give review a state machine.
--
-- Until now every /triage result was computed, returned and thrown away.
-- Langfuse had traces, but traces are observability in a third party with
-- retention limits - not something you can hand an auditor, query per tenant,
-- or build a review queue on.
--
-- Two tables, with different rules:
--   triage_events      - current state of each triaged message. Mutable: a
--                        reviewer approves, edits, sends.
--   triage_event_audit - append-only log of how it got to that state. The
--                        app role is granted INSERT and SELECT only, so
--                        "immutable" is enforced by the database rather than
--                        by everyone remembering not to write an UPDATE.

alter table triage_events
    add column if not exists channel text not null default 'api',
    -- Citations as stored JSON rather than a join table: they are a snapshot
    -- of what was cited at decision time. If the knowledge base is later
    -- edited or a chunk deleted, the record of what the customer was actually
    -- told must not change with it.
    add column if not exists citations jsonb not null default '[]'::jsonb,
    add column if not exists status text not null default 'needs_review',
    add column if not exists requested_by uuid references users(id),
    add column if not exists final_reply text,
    add column if not exists latency_ms integer,
    add column if not exists model text;

-- needs_review: a rule sent it to a human (see app/services/escalation.py).
-- draft_ready:  the system is willing to answer; whether that can be sent
--               without a human is a per-tenant policy decision, not a
--               property of the message, so it is a separate step.
-- approved / edited: a reviewer accepted the draft, or rewrote it.
-- sent:      the reply went to the customer.
-- rejected:  the reviewer discarded the draft and handled it another way.
do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'triage_events_status_check'
    ) then
        alter table triage_events add constraint triage_events_status_check
            check (status in ('needs_review', 'draft_ready', 'approved', 'edited', 'sent', 'rejected'));
    end if;
end
$$;

-- The review queue is always "this tenant's oldest unresolved first".
create index if not exists triage_events_queue_idx
    on triage_events (tenant_id, status, created_at desc);

create table if not exists triage_event_audit (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    event_id uuid not null references triage_events(id) on delete cascade,
    -- Null actor means the system itself acted (the initial triage decision),
    -- as opposed to a person. Both are auditable events.
    actor_user_id uuid references users(id),
    action text not null,
    from_status text,
    to_status text,
    detail jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists triage_event_audit_event_idx
    on triage_event_audit (tenant_id, event_id, created_at);

alter table triage_event_audit enable row level security;
alter table triage_event_audit force row level security;

drop policy if exists tenant_isolation_triage_event_audit on triage_event_audit;
create policy tenant_isolation_triage_event_audit on triage_event_audit
    using (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Append-only, enforced. 0002 granted the app role all four verbs on every
-- table (and on future ones via default privileges), so take two back here.
revoke update, delete on triage_event_audit from triage_app;
