-- Supabase installs extensions (including pgvector) into a dedicated
-- "extensions" schema, not "public". The admin role's default search_path
-- includes it, which is why 0001's `create extension if not exists vector`
-- succeeded and hid this - but triage_app's search_path did not, so every
-- query against a `vector` column failed with "type vector does not exist"
-- as soon as the unprivileged role (the one that actually matters for RLS)
-- tried to use it.
--
-- Local docker-compose Postgres has no "extensions" schema; this is a no-op
-- there since the vector type already lives in the default search_path.
do $$
begin
    if exists (select 1 from pg_namespace where nspname = 'extensions') then
        grant usage on schema extensions to triage_app;
        execute 'alter role triage_app set search_path = public, extensions';
    end if;
end
$$;
