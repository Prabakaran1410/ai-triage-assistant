# Migrations

Run with `python scripts/migrate.py` against `DATABASE_URL` (the admin/superuser
connection — Supabase's `postgres` role, or local `triage` user in
docker-compose). Files apply in filename order, and are safe to re-run.

## After `0002_app_role.sql`

That migration creates `triage_app`, an unprivileged role the API uses at
runtime instead of `postgres`, because Postgres never enforces row-level
security for a table's owner or a `BYPASSRLS` role - which `postgres` is by
default on Supabase. Connecting as `postgres` at runtime would make every RLS
policy in `0001_init.sql` silently do nothing.

Set the role's password once, out of band (never commit it):

- **Supabase:** Dashboard -> Database -> Roles -> `triage_app` -> reset password
- **Local/docker-compose:** `alter role triage_app with password 'something';`
  run once via `psql`

Then point the app at it with a *second* env var, `APP_DATABASE_URL`, using
that role instead of `postgres`/`triage`:

```
APP_DATABASE_URL=postgresql+asyncpg://triage_app.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

`DATABASE_URL` (admin) stays for migrations only; `APP_DATABASE_URL`
(unprivileged, RLS-enforced) is what `app/core/db.py` and the tenant isolation
test actually connect with.
