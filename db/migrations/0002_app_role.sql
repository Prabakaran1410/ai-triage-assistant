-- Postgres never applies row-level security to a table's owner or to a role
-- with BYPASSRLS - which the "postgres" superuser Supabase hands out by
-- default has. The isolation test in tests/test_tenant_isolation.py caught
-- this: connecting as "postgres" saw every tenant's rows regardless of RLS
-- policies. FORCE ROW LEVEL SECURITY does not fix it for superusers either.
--
-- Fix: the API never connects as "postgres" at runtime. It uses a dedicated,
-- unprivileged role that owns nothing and cannot bypass RLS. Only migrations
-- (run by a human/CI with the admin URL) use "postgres".

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'triage_app') then
        create role triage_app with login noinherit nosuperuser nocreatedb nocreaterole nobypassrls;
    end if;
end
$$;

grant usage on schema public to triage_app;
grant select, insert, update, delete on all tables in schema public to triage_app;
alter default privileges in schema public
    grant select, insert, update, delete on tables to triage_app;

-- Belt and suspenders: force RLS even for the table owner (irrelevant for
-- triage_app, which never owns these tables, but harmless and correct).
alter table users force row level security;
alter table knowledge_chunks force row level security;
alter table triage_events force row level security;

-- Password is set out-of-band (Supabase dashboard: Database -> Roles, or
-- `alter role triage_app with password '...'` run by hand) and is never
-- committed here. See db/migrations/README.md.
