-- A knowledge base was loadable only by script, and only wholesale: the
-- ingest path replaced every chunk a tenant had. Managing documents one at
-- a time needs the document itself to exist as a row, not just the pieces
-- it was split into.
--
-- The original text is kept alongside the chunks so the console can show a
-- customer what they uploaded, and so a document can be re-chunked later
-- (different size, better splitter) without asking them to upload it again.

create table if not exists knowledge_sources (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    -- Stable, human-meaningful handle: what citations point at.
    source_id text not null,
    title text not null,
    content text not null,
    chunk_count integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, source_id)
);

create index if not exists knowledge_sources_tenant_idx
    on knowledge_sources (tenant_id, updated_at desc);

alter table knowledge_sources enable row level security;
alter table knowledge_sources force row level security;

drop policy if exists tenant_isolation_knowledge_sources on knowledge_sources;
create policy tenant_isolation_knowledge_sources on knowledge_sources
    using (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Ordering matters when a reviewer reads chunks of one document: without
-- this they come back in whatever order the index happens to return.
alter table knowledge_chunks add column if not exists chunk_index integer not null default 0;

create index if not exists knowledge_chunks_source_idx
    on knowledge_chunks (tenant_id, source_id, chunk_index);
